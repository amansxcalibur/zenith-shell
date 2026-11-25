import cairo

from fabric.widgets.box import Box

from config import namespaces
from config.info import IS_WAYLAND

from utils.colors import bind_theme
from utils.helpers import keep_window

from wm import glass_mode

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window


# Moving the widget between a PopSlot and a FlyingOverlay leaves a gap
# where neither has painted it yet, so a snapshot "ghost" stays on the
# *old* surface until the *new* one has painted.
# Although I gotta say it's pretty cute when the slot used to "blink"
HANDOFF_FRAMES = 2  # 1 paint + 1 frame of margin for the compositor
HANDOFF_TIMEOUT_MS = 150  # fallback if the receiving window never paints

FLIGHT_US = 300_000
# a slow frame moves the flight on by at most this much, so a hiccup slows it
# down instead of making it jump
MAX_STEP_US = 33_000


def snapshot_widget(widget: Gtk.Widget) -> Gtk.Image | None:
    if not widget.get_mapped():
        return None
    alloc = widget.get_allocation()
    if alloc.width <= 0 or alloc.height <= 0:
        return None
    scale = widget.get_scale_factor()
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, alloc.width * scale, alloc.height * scale
    )
    surface.set_device_scale(scale, scale)
    widget.draw(cairo.Context(surface))
    ghost = Gtk.Image.new_from_surface(surface)
    ghost.set_size_request(alloc.width, alloc.height)
    ghost.show()
    return ghost


def after_frames(widget: Gtk.Widget, callback, frames: int = HANDOFF_FRAMES):
    clock = widget.get_frame_clock()
    if clock is None:  # not realized: nothing will paint, don't wait
        callback()
        return

    state = {"left": frames, "done": False}

    def finish():
        if state["done"]:
            return
        state["done"] = True
        clock.disconnect(paint_id)
        callback()

    def on_after_paint(_clock):
        state["left"] -= 1
        if state["left"] <= 0:
            finish()
        else:
            widget.queue_draw()  # an idle window won't paint again on its own

    paint_id = clock.connect("after-paint", on_after_paint)
    GLib.timeout_add(HANDOFF_TIMEOUT_MS, lambda: finish() and False)
    widget.queue_draw()


class PopSlot(Box):
    def __init__(self, children, overlay=None, target_size=(320, 200), **kwargs):
        super().__init__(**kwargs)
        self.overlay = overlay or FlyingOverlay.get_shared()
        self.target_size = target_size
        self.child = children
        self.child.quick_settings_slot = self
        self.add(children)

    # called by the child
    def pop_out(self):
        get_size = getattr(self.child, "get_expanded_size", None)
        self.overlay.pop_out(self, get_size() if get_size else self.target_size)

    def dismiss(self):
        if self.overlay.source_slot is self:
            self.overlay.dismiss()

    # the rest is called by FlyingOverlay
    def release(self):
        alloc = self.get_allocation()
        self.set_size_request(alloc.width, alloc.height)
        self.remove(self.child)
        return self.child

    def show_ghost(self, ghost):
        self._ghost = ghost
        self.pack_start(ghost, True, True, 0)

    def clear_ghost(self, ghost=None):
        current = getattr(self, "_ghost", None)
        if current is None or (ghost is not None and current is not ghost):
            return
        self.remove(current)
        self._ghost = None

    def restore(self, widget):
        self.clear_ghost()
        self.pack_start(widget, True, True, 0)
        widget.show()
        self.set_size_request(-1, -1)

    def on_popped(self):
        if hasattr(self.child, "on_popped"):
            self.child.on_popped()

    def on_restored(self):
        if hasattr(self.child, "on_restored"):
            self.child.on_restored()


class FlyingOverlay(Window):
    _shared = None

    @classmethod
    def get_shared(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def __init__(self):
        if IS_WAYLAND:
            super().__init__(
                layer="overlay",
                title=namespaces.FLYING,
                keyboard_mode="on-demand",
                anchor="top bottom left right",
                visible=False,
                all_visible=False,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)
        else:
            super().__init__(
                geometry="top",
                type="top-level",
                type_hint="utility",
                visible=False,
                all_visible=False,
            )
            geometry = Gdk.Display.get_default().get_primary_monitor().get_geometry()
            self.set_default_size(geometry.width, geometry.height)

        if glass_mode():
            self.add_style_class("glass")
        bind_theme(self)

        # don't close me :(
        self.connect("delete-event", lambda *_: keep_window(self))

        self.content_frame = Box()
        self.fixed_canvas = Gtk.Fixed()
        self.fixed_canvas.put(self.content_frame, 0, 0)
        self.flying_container = Box(name="flying-tile", children=self.fixed_canvas)
        self.add(self.flying_container)

        self.screen_width = self.screen_height = 0
        self.curr_x = self.curr_y = self.curr_w = self.curr_h = 0.0
        self.source_slot = None
        self.source_widget = None
        self._closing = False
        self._size_watch = None

        self._tick_id = None
        self._from = self._to = (0.0, 0.0, 0.0, 0.0)
        self._progress = 0.0
        self._last_frame = None
        self._on_complete = None

        self.connect("button-press-event", self._on_background_click)
        self.add_keybinding("Escape", lambda *_: self.dismiss())
        self.connect("focus-out-event", self._on_focus_out)

    def _on_focus_out(self, *_):
        if not self._has_open_dialog():
            self.dismiss()

    def _has_open_dialog(self) -> bool:
        return IS_WAYLAND and any(
            window.get_visible() and window.get_transient_for() is self
            for window in Gtk.Window.list_toplevels()
        )

    def _on_background_click(self, _widget, event):
        if self.source_slot is None:
            return False
        if (
            self.curr_x <= event.x <= self.curr_x + self.curr_w
            and self.curr_y <= event.y <= self.curr_y + self.curr_h
        ):
            return False  # click landed on the popped widget itself
        self.dismiss()
        return True

    def _centered(self, w, h):
        return ((self.screen_width - w) // 2, (self.screen_height - h) // 2, w, h)

    def pop_out(self, slot: PopSlot, target_size=(320, 200)):
        if self.source_slot is not None:
            return

        success, x, y = slot.get_window().get_origin()
        if IS_WAYLAND:
            success, win_x, win_y = self._get_absolute_position(slot)
            x, y = x + win_x, y + win_y
        if not success:
            return

        alloc = slot.get_allocation()
        start = (x + alloc.x, y + alloc.y, alloc.width, alloc.height)

        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_point(int(start[0]), int(start[1]))
        geometry = (monitor or display.get_primary_monitor()).get_geometry()
        self.screen_width, self.screen_height = geometry.width, geometry.height

        self.source_slot = slot
        self.orig = start
        GLib.idle_add(self._begin_flight, start, target_size)

    def _get_absolute_position(self, widget):
        toplevel = widget.get_toplevel()
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_window(
            toplevel.get_window()
        ) or display.get_monitor(0)
        geo = monitor.get_geometry()
        win_alloc = toplevel.get_allocation()
        Edge = GtkLayerShell.Edge

        def axis(lo, hi, size, start, length):
            at_lo = GtkLayerShell.get_anchor(toplevel, lo)
            at_hi = GtkLayerShell.get_anchor(toplevel, hi)
            if at_lo:
                return start + GtkLayerShell.get_margin(toplevel, lo)
            if at_hi:
                return start + length - GtkLayerShell.get_margin(toplevel, hi) - size
            return start + (length - size) // 2

        win_x = axis(Edge.LEFT, Edge.RIGHT, win_alloc.width, geo.x, geo.width)
        win_y = axis(Edge.TOP, Edge.BOTTOM, win_alloc.height, geo.y, geo.height)
        return True, win_x, win_y

    def _begin_flight(self, start, target_size):
        slot = self.source_slot
        # keep the slot looking unchanged until the overlay has painted the tile
        ghost = snapshot_widget(slot.child)
        self.source_widget = slot.release()
        if ghost is not None:
            slot.show_ghost(ghost)
        self.content_frame.pack_start(self.source_widget, True, True, 0)
        self.set_pass_through(False)
        self.flying_container.add_style_class("darken")

        self._place(*start)  # before mapping, so the first frame is at the slot
        self.show_all()
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)

        # let the child grow (e.g. Tile -> menu) only now:
        # - not before release(): the dashboard would re-lay out with the big
        #   child and release() would pin the slot at that inflated size
        # - not before show_all(): an unmapped GtkStack skips its transition
        slot.on_popped()

        self._animate_to(self._centered(*target_size), self._land)
        if ghost is not None:
            after_frames(self, lambda: slot.clear_ghost(ghost))
        return False

    def _land(self):
        widget = self.source_widget
        self._size_watch = (
            widget,
            widget.connect("size-allocate", self._on_content_resized),
        )

    def _unwatch_content_size(self):
        if self._size_watch is not None:
            widget, handle = self._size_watch
            widget.disconnect(handle)
            self._size_watch = None

    def _on_content_resized(self, widget, _alloc):
        w = widget.get_preferred_width()[1]
        h = widget.get_preferred_height_for_width(w)[1]
        if (w, h) != self._to[2:]:
            self._animate_to(self._centered(w, h))

    def dismiss(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

        if self.source_slot is None or self._closing:
            return
        self._closing = True
        self._unwatch_content_size()
        self.source_slot.on_restored()
        self.set_pass_through(True)
        self.flying_container.remove_style_class("darken")

        if self.source_slot.get_mapped():
            self._animate_to(self.orig, self._finish_dismiss)
        else:  # slot is off screen (e.g. mid-transition): just shrink away
            self.add_style_class("fade-out")
            self._animate_to((self.curr_x, self.curr_y, 0, 0), self._finish_dismiss)

    def _finish_dismiss(self):
        slot, widget = self.source_slot, self.source_widget
        # keep showing the tile here until the slot has painted the real one
        ghost = snapshot_widget(widget) if slot.get_mapped() else None
        self.content_frame.remove(widget)
        if ghost is not None:
            self.content_frame.pack_start(ghost, True, True, 0)
        slot.restore(widget)

        def complete():
            self.hide()
            if ghost is not None:
                self.content_frame.remove(ghost)
            self.remove_style_class("fade-out")
            self.source_slot = self.source_widget = None
            self._closing = False

        if ghost is not None:
            after_frames(slot, complete)
        else:
            complete()

    def _place(self, x, y, w, h):
        self.curr_x, self.curr_y, self.curr_w, self.curr_h = x, y, w, h
        self.content_frame.set_size_request(int(w), int(h))
        self.fixed_canvas.move(self.content_frame, int(x), int(y))

    def _animate_to(self, target, on_complete=None):
        self._from = (self.curr_x, self.curr_y, self.curr_w, self.curr_h)
        self._to = target
        self._progress = 0.0
        self._last_frame = None
        self._on_complete = on_complete
        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._on_tick)

    def _on_tick(self, _widget, clock):
        now = clock.get_frame_time()
        if self._last_frame is not None:
            step = min(now - self._last_frame, MAX_STEP_US) / FLIGHT_US
            self._progress = min(self._progress + step, 1.0)
        self._last_frame = now

        eased = 1 - (1 - self._progress) ** 3  # ease-out cubic
        self._place(*(a + (b - a) * eased for a, b in zip(self._from, self._to)))
        if self._progress < 1.0:
            return True

        self._tick_id = None
        callback, self._on_complete = self._on_complete, None
        if callback:
            callback()
        return False
