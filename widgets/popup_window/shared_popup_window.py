from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer

from config.info import SHELL_NAME, IS_WAYLAND
from modules.core.bottom.dock.placement import DockEdge, current_placement

from services.animator import Animator
from services.power_profiles import power_profiles_service

from utils.colors import bind_theme
from utils.helpers import keep_window, get_absolute_wayland_widget_position
from widgets.clipping_box import ClippingBox

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gdk, GLib, Gtk  # type: ignore

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window


class SharedPopupWindow(Window):
    _instance = None
    _initialized = False

    # constants
    DEFAULT_TRANSITION_DURATION = 250
    DEFAULT_TRANSITION_TYPE = "crossfade"
    UNHOVER_DELAY_MS = 250
    HIDE_DELAY_MS = 300
    POPUP_OFFSET = 3  # pixels between the dock and the popup
    WINDOW_PADDING = 5  # the popup's own padding, around its child
    PAINT_TIMEOUT_MS = 200  # longest the contents stay hidden awaiting a paint

    # animation constants
    ANIMATION_BEZIER = (0.15, 0.88, 0.68, 0.95)
    ANIMATION_DURATION = 0.3

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        transition_duration=DEFAULT_TRANSITION_DURATION,
        transition_type=DEFAULT_TRANSITION_TYPE,
        **kwargs,
    ):
        if self._initialized:
            return

        self._placement = current_placement()
        if IS_WAYLAND:
            # no exclusive zone: the compositor keeps the fixed-side margin
            # clear of the dock, these only add the offset from it
            anchor, margin = {
                DockEdge.BOTTOM: ("bottom left", (0, 0, 3, 0)),
                DockEdge.LEFT: ("top left", (0, 0, 0, 3)),
                DockEdge.RIGHT: ("top right", (0, 3, 0, 0)),
            }[self._placement.edge]
            super().__init__(
                layer="top",
                keyboard_mode="on-demand",
                anchor=anchor,
                exclusivity="none",
                margin=margin,
                visible=False,
                all_visible=False,
            )
        else:
            super().__init__(
                layer="top",
                type_hint="normal",
                visible=False,
                all_visible=False,
                **kwargs,
            )
        self._initialized = True
        self.set_role(f"{SHELL_NAME}-popup")

        bind_theme(self)

        self.pointing_widget = None
        self.pointing_widget_size_alloc_hook = None

        # position along the dock: x for a bottom dock, y for a side dock
        self.target_along = 0

        # last (width, height) sent to the X server. On X11, get_allocation()
        # lags behind a resize until the WM's ConfigureNotify arrives, so any
        # move computed from it in between puts the bottom below the baseline.
        self._committed_size = None
        # size sent via move_resize whose allocation hasn't arrived yet
        self._pending_size = None

        # X11: waiting for the first paint after a show (see _hide_until_painted)
        self._paint_draw_hook = None
        self._paint_size = None
        self._paint_idle_ref = None
        self._paint_timeout_ref = None

        # hover state tracking
        self.is_hover_popup = False
        self.is_hover_widget = False

        # timer references
        self.unhover_delay_ref = None
        self.hide_delay_ref = None

        # widget-popup mapping
        self.child_pointing_widget_dict = {}

        self._animations_enabled = self._should_animate()
        power_profiles_service.connect("changed", self._on_power_profile_changed)

        self._initialize_animators()
        self._initialize_ui(transition_duration, transition_type)

        # disconnect the X11Window geometry enforcement hook
        if hasattr(self, "_size_allocate_hook") and self._size_allocate_hook:
            try:
                self.handler_disconnect(self._size_allocate_hook)
                self._size_allocate_hook = None
            except Exception as e:
                logger.debug(
                    f"Could not disconnect size allocate hook. This could cause jitter: {e}"
                )

        self.event_box.connect(
            "enter-notify-event",
            lambda x, y: self._on_hover_popup(event=y, state=True),
        )
        self.event_box.connect(
            "leave-notify-event",
            lambda x, y: self._on_hover_popup(event=y, state=False),
        )

        self.connect("delete-event", self.on_delete_event)
        # self.connect("configure-event", self.on_window_move)

    # def on_window_move(self, widget, event):
    #     print(
    #         f"Window moved to ({event.x}, {event.y}), size = {event.width}x{event.height}"
    #     )
    #     ...

    @staticmethod
    def _should_animate() -> bool:
        # X11 keeps gliding and interpolating its size in power-saver
        return not IS_WAYLAND or power_profiles_service.active_profile != "power-saver"

    def _on_power_profile_changed(self, *_):
        self._animations_enabled = self._should_animate()
        duration = self.DEFAULT_TRANSITION_DURATION if self._animations_enabled else 0
        self.stack.set_transition_duration(duration)
        self.revealer.set_transition_duration(duration)
        self.animator.duration = (
            self.ANIMATION_DURATION if self._animations_enabled else 0
        )  # seconds

    def _initialize_ui(self, transition_duration, transition_type):
        self.stack = Stack(
            transition_type=transition_type,
            transition_duration=transition_duration if self._animations_enabled else 0,
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.revealer = Revealer(
            transition_duration=transition_duration if self._animations_enabled else 0,
            transition_type=transition_type,
            child=self.stack,
            child_revealed=False,
        )

        self.event_box = EventBox(child=self.revealer)
        self.children = Box(
            children=ClippingBox(style="border-radius:15px", children=self.event_box),
            style="background-color:rgba(0,0,0,0.1); padding:5px; border-radius:20px",
        )

    def _initialize_animators(self):
        self.animator = Animator(
            bezier_curve=self.ANIMATION_BEZIER,
            duration=self.ANIMATION_DURATION if self._animations_enabled else 0,
            tick_widget=self,
            notify_value=self._on_animator_tick,
        )

    def _on_animator_tick(self, p, *_):
        self.target_along = p.value
        self.place_popup(p.value)

    def add_child(self, pointing_widget, child):
        if not isinstance(pointing_widget, EventBox):
            logger.warning(
                f"The widget ({pointing_widget.get_name()}) SharedPopupWindow is pointing to must be an EventBox instance"
            )

        pointing_widget.connect("enter-notify-event", self._on_hover_widget, True)
        pointing_widget.connect("leave-notify-event", self._on_hover_widget, False)

        self.child_pointing_widget_dict[pointing_widget] = child
        self.stack.add_named(child, child.get_name())

    def _on_hover_popup(self, event, state):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return

        self.is_hover_popup = state
        self._handle_window_visibility()

    def _on_hover_widget(self, source, event, state):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return

        self.is_hover_widget = state

        if state:
            if source is not self.pointing_widget:
                self._update_pointing_widget(source)

            next_visible_child = self.child_pointing_widget_dict[source]
            self.stack.set_visible_child(next_visible_child)

            def _set_position():
                along = self._calculate_popup_position()
                if along is not None:
                    if self._animations_enabled:
                        self.animate_to_position(along)
                    else:
                        self.place_popup(along)
                return False

            if self.get_visible():
                GLib.idle_add(_set_position)
            else:
                # an idle would run after the window has been shown where
                # its last child left it
                self._place_before_show()

        self._handle_window_visibility()

    def _place_before_show(self):
        along = self._calculate_popup_position()
        if along is None:
            return
        self.target_along = along

        # unmapped, the stack has already switched to the new child
        _, nat = self.get_preferred_size()
        width, height = nat.width, nat.height
        self._pending_size = None
        self._committed_size = (width, height)

        if IS_WAYLAND:
            self._set_along_margin(along, width, height)
        else:
            self.move(*self._x11_position(along, width, height))
            self._hide_until_painted(width, height)

    def _set_contents_hidden(self, hidden: bool) -> bool:
        """X11: hide the window's contents through the compositor."""
        xwindow = getattr(self, "_xwindow", None)
        if xwindow is None:  # no Xlib, or not drawn even once
            return False

        # GTK's own opacity is applied when it paints, which is too late here
        atom = self._xdisplay.intern_atom("_NET_WM_WINDOW_OPACITY")
        if hidden:
            cardinal = self._xdisplay.intern_atom("CARDINAL")
            xwindow.change_property(atom, cardinal, 32, [0])
        else:
            xwindow.delete_property(atom)
        self._xdisplay.flush()
        return True

    def _hide_until_painted(self, width: int, height: int):
        # A window shown at a new size gets a fresh, uninitialised buffer, and
        # the compositor can present it before our first paint: a frame of
        # white noise whenever the child changed while the popup was hidden.
        self._cancel_paint_wait()
        if not self._set_contents_hidden(True):
            return
        self._paint_size = (width, height)
        self._paint_draw_hook = self.connect_after("draw", self._on_paint_after_show)
        self._paint_timeout_ref = GLib.timeout_add(
            self.PAINT_TIMEOUT_MS, self._on_paint_timeout
        )

    def _on_paint_after_show(self, *_):
        alloc = self.get_allocation()
        # the first draw can still be at the previous child's size
        if self._paint_size in (None, (alloc.width, alloc.height)):
            self.disconnect(self._paint_draw_hook)
            self._paint_draw_hook = None
            # once this frame is painted; a default idle waits behind the
            # frames that follow
            self._paint_idle_ref = GLib.idle_add(
                self._show_contents, priority=GLib.PRIORITY_HIGH
            )
        return False

    def _on_paint_timeout(self):
        self._paint_timeout_ref = None
        if self._paint_draw_hook is None:
            return False
        # never painted at the expected size: settle for the next paint at
        # any size. A blocked main loop can bring us here before the first.
        self._paint_size = None
        self.queue_draw()
        return False

    def _show_contents(self):
        self._paint_idle_ref = None  # this source ends by returning False
        self._cancel_paint_wait()
        self.get_display().sync()  # the paint goes out on GDK's connection first
        self._set_contents_hidden(False)
        return False

    def _cancel_paint_wait(self):
        if self._paint_draw_hook is not None:
            self.disconnect(self._paint_draw_hook)
            self._paint_draw_hook = None
        for ref in (self._paint_idle_ref, self._paint_timeout_ref):
            if ref is not None:
                GLib.source_remove(ref)
        self._paint_idle_ref = self._paint_timeout_ref = None

    def _update_pointing_widget(self, source):
        if (
            self.pointing_widget is not None
            and self.pointing_widget_size_alloc_hook is not None
        ):
            self.pointing_widget.disconnect(self.pointing_widget_size_alloc_hook)
            self.pointing_widget_size_alloc_hook = None

        self.pointing_widget = source

        self.pointing_widget_size_alloc_hook = self.pointing_widget.connect(
            "size-allocate",
            lambda w, alloc: self._on_widget_size_allocate(source),
        )

    def _on_widget_size_allocate(self, source_widget):
        if source_widget is not self.pointing_widget or not self.get_visible():
            return

        along = self._calculate_popup_position()
        if along is None:
            return

        if self.animator.playing:
            if self._animations_enabled:
                self.animate_to_position(along)  # pauses, updates and plays
            else:
                self.animator.stop()
                self.place_popup(along)
            return

        else:
            self.place_popup(along)

    def _calculate_popup_position(self) -> float | None:
        """Where the popup should start along the dock, centred on the widget."""
        if not self.pointing_widget:
            return None

        if self._placement.vertical:
            return self._calculate_side_dock_position()

        widget_alloc = self.pointing_widget.get_allocation()
        _, popup_widget_alloc = self.child_pointing_widget_dict[
            self.pointing_widget
        ].get_preferred_width()

        try:
            _, root_x, _ = self.pointing_widget.get_window().get_origin()

            # print("Position of widget: ", root_x + widget_alloc.x)
            # print("popup widg final size", popup_widget_alloc)
            # print("Position to be of popup: ", root_x + widget_alloc.x + widget_alloc.width/2 - popup_widget_alloc/2)
            # print("------------------------------------------------------")

            # center horizontally, place above the widget
            target_x = (
                root_x
                + widget_alloc.x
                + widget_alloc.width / 2
                - popup_widget_alloc / 2
            )

            if IS_WAYLAND:
                success, x, _ = get_absolute_wayland_widget_position(
                    self.pointing_widget
                )
                if success:
                    target_x += x

            return target_x

        except Exception as e:
            logger.error(f"Failed to calculate popup position: {e}")
            return None

    def _calculate_side_dock_position(self) -> float | None:
        widget = self.pointing_widget
        toplevel = widget.get_toplevel()
        coords = widget.translate_coordinates(toplevel, 0, 0)
        if coords is None:
            return None

        # a side dock spans the screen, so its window starts at the top
        _, popup_height = self.child_pointing_widget_dict[widget].get_preferred_height()
        popup_height += 2 * self.WINDOW_PADDING
        return coords[1] + widget.get_allocated_height() / 2 - popup_height / 2

    def _side_dock_x(self, width: int) -> int:
        """X11 only: the fixed x next to a side dock; Wayland anchors instead."""
        thickness = self.pointing_widget.get_toplevel().get_allocated_width()
        if self._placement.edge is DockEdge.LEFT:
            return thickness + self.POPUP_OFFSET
        return self.get_screen().get_width() - thickness - width - self.POPUP_OFFSET

    @staticmethod
    def _get_anchor_widget(widget):
        # nearest ancestor (or the widget itself) marked with
        # `is_popup_anchor = True`; lets containers whose children animate
        # (e.g. dock modules raising on hover) provide a stable baseline
        w = widget
        while w is not None:
            if getattr(w, "is_popup_anchor", False):
                return w
            w = w.get_parent()
        return widget

    def _get_target_baseline(self):
        if not self.pointing_widget:
            return 0
        anchor = self._get_anchor_widget(self.pointing_widget)
        _, _, anchor_root_y = anchor.get_window().get_origin()
        return anchor_root_y + anchor.get_allocation().y - self.POPUP_OFFSET

    def _clamp_x(self, x: int, width: int | None = None) -> int:
        screen = self.get_screen()
        if screen is None:
            return x
        w = width if width is not None else self._current_size()[0]
        return max(self.POPUP_OFFSET, min(x, screen.get_width() - w))

    def _clamp_along(self, along: float, width: int, height: int) -> int:
        if self._placement.vertical:
            return self._clamp_y(along, height)
        return self._clamp_x(along, width)

    def _x11_position(self, along: float, width: int, height: int) -> tuple[int, int]:
        along = int(self._clamp_along(along, width, height))
        if self._placement.vertical:
            return self._side_dock_x(width), along
        return along, int(self._get_target_baseline() - height)

    def _set_along_margin(self, along: float, width: int, height: int) -> None:
        edge = (
            GtkLayerShell.Edge.TOP
            if self._placement.vertical
            else GtkLayerShell.Edge.LEFT
        )
        GtkLayerShell.set_margin(
            self, edge, int(self._clamp_along(along, width, height))
        )

    def _clamp_y(self, y: int, height: int | None = None) -> int:
        screen = self.get_screen()
        if screen is None:
            return y
        h = height if height is not None else self._current_size()[1]
        return max(0, min(y, screen.get_height() - h))

    def _handle_window_visibility(self):
        is_hovered = self.is_hover_widget or self.is_hover_popup

        if not is_hovered:
            if self.unhover_delay_ref is not None:
                GLib.source_remove(self.unhover_delay_ref)
            self.unhover_delay_ref = GLib.timeout_add(
                self.UNHOVER_DELAY_MS, self._check_and_hide
            )
        else:
            # show immediately, cancel any pending hides
            self._cancel_pending_timers()

            self.set_visible(True)
            self.revealer.reveal()

    def _cancel_pending_timers(self):
        if self.hide_delay_ref is not None:
            GLib.source_remove(self.hide_delay_ref)
            self.hide_delay_ref = None

        if self.unhover_delay_ref is not None:
            GLib.source_remove(self.unhover_delay_ref)
            self.unhover_delay_ref = None

    def _check_and_hide(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            self.revealer.unreveal()
            self.animator.pause()

            def _do_hide():
                self.set_visible(False)
                self.hide_delay_ref = None
                return False

            self.hide_delay_ref = GLib.timeout_add(self.HIDE_DELAY_MS, _do_hide)

        self.unhover_delay_ref = None
        return False

    def _current_along(self) -> int:
        _, x, y = self.get_window().get_origin()
        if IS_WAYLAND:
            _, wayland_x, wayland_y = get_absolute_wayland_widget_position(self)
            x, y = x + wayland_x, y + wayland_y
        return y if self._placement.vertical else x

    def animate_to_position(self, target_along):
        start = self._current_along()
        child = self.child_pointing_widget_dict[self.pointing_widget]
        self.animator.pause()
        self.animator.handler_block_by_func(self._on_animator_tick)
        self.animator.min_value = start
        self.animator.max_value = self._clamp_along(
            target_along,
            width=child.get_preferred_width()[1],
            height=child.get_preferred_height()[1] + 2 * self.WINDOW_PADDING,
        )
        self.animator.value = start
        self.animator.handler_unblock_by_func(self._on_animator_tick)
        self.animator.play()

    def _current_size(self) -> tuple[int, int]:
        if self._pending_size is not None:
            return self._pending_size
        if self._committed_size is not None:
            return self._committed_size
        alloc = self.get_allocation()
        return alloc.width, alloc.height

    def place_popup(self, along: float | None = None):
        if along is None:
            along = self.target_along
        else:
            self.target_along = along

        win = self.get_window()
        if win:
            width, height = self._current_size()
            if IS_WAYLAND:
                self._set_along_margin(along, width, height)
            else:
                win.move(*self._x11_position(along, width, height))

    def do_check_resize(self):
        if (
            not IS_WAYLAND
            and getattr(self, "pointing_widget", None)
            and self.get_mapped()
        ):
            try:
                _, nat = self.get_preferred_size()
                win = self.get_window()
                # compare against what we last sent; the GdkWindow size lags
                # until ConfigureNotify, which would resend the same request
                if win and (nat.width, nat.height) != self._current_size():
                    x, y = self._x11_position(self.target_along, nat.width, nat.height)
                    win.move_resize(x, y, nat.width, nat.height)
                    self._pending_size = (nat.width, nat.height)
            except Exception as e:
                logger.error(f"do_check_resize atomic move_resize failed: {e}")

        Gtk.Window.do_check_resize(self)

    def do_size_allocate(self, alloc):
        # uses fresh allocation to move window before it extends below baseline
        if not hasattr(self, "pointing_widget"):
            return

        # GTK may allocate from an older ConfigureNotify after we already sent a
        # newer move_resize. Positioning from that stale height would push the
        # bottom off the baseline, so keep using the pending size until the
        # allocation catches up.
        alloc_size = (alloc.width, alloc.height)
        if self._pending_size == alloc_size or not self.get_mapped():
            self._pending_size = None
        if self._pending_size is None:
            self._committed_size = alloc_size

        if self.pointing_widget and self.get_mapped():
            try:
                win = self.get_window()
                if win:
                    width, height = self._current_size()
                    if IS_WAYLAND:
                        self._set_along_margin(self.target_along, width, height)
                    else:
                        win.move(*self._x11_position(self.target_along, width, height))

            except Exception as e:
                logger.error(f"do_size_allocate Y position failed: {e}")

        Gtk.Window.do_size_allocate(self, alloc)

    def on_delete_event(self, *_):
        # don't close me :(
        return keep_window(self)
