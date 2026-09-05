import cairo

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack

from config.info import IS_WAYLAND

if IS_WAYLAND:
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window

from fabric.core.service import Signal, Service

from services.animator import Animator

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib  # type: ignore


class PopSlot(Box):
    def __init__(self, children, overlay=None, target_size=(320, 200), **kwargs):
        super().__init__(**kwargs)
        self.overlay = overlay or FlyingOverlay.get_shared()

        self.add(children)
        self.target_size = (
            children.get_expanded_size()
            if hasattr(children, "get_expanded_size")
            else target_size
        )

        self.child = children
        self.child.quick_settings_slot = self

    # called by the child
    def pop_out(self):
        expanded_factory = getattr(self.child, "build_expanded_content", None)
        # not using size groups, cuz I'm not dealing with dynamic ones yet
        self.target_size = (
            self.child.get_expanded_size()
            if hasattr(self.child, "get_expanded_size")
            else self.target_size
        )
        self.overlay.pop_out(
            self, target_size=self.target_size, expanded_factory=expanded_factory
        )

    # called by FlyingOverlay, not by tile authors
    def release(self):
        alloc = self.get_allocation()
        self.set_size_request(alloc.width, alloc.height)
        self.remove(self.child)
        return self.child

    def show_ghost(self, ghost_widget):
        self._ghost = ghost_widget
        self.pack_start(ghost_widget, True, True, 0)
        ghost_widget.show()

    def restore(self, widget):
        if getattr(self, "_ghost", None) is not None:
            self.remove(self._ghost)
            self._ghost = None
        self.pack_start(widget, True, True, 0)
        widget.show()
        self.set_size_request(-1, -1)

    # called by FlyingOverlay
    def on_flight_landed(self): ...

    def on_flight_begin_restored(self):
        if hasattr(self.child, "on_restored"):
            self.child.on_restored()

    def dismiss(self):
        self.overlay.request_dismiss(self)


class FlyingOverlay(Window, Service):
    @Signal
    def flight_restored(self, slot: PopSlot): ...

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

        # recomputed every pop
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        if not IS_WAYLAND:
            geometry = monitor.get_geometry()
            self.screen_width = geometry.width
            self.screen_height = geometry.height
            self.set_default_size(self.screen_width, self.screen_height)

        self.content_frame = Box()
        self.content_stack = Stack(transition_duration=180, transition_type="crossfade")
        self.content_frame.pack_start(self.content_stack, True, True, 0)

        self.fixed_canvas = Gtk.Fixed()
        self.fixed_canvas.put(self.content_frame, 0, 0)

        self.flying_container = Box(name="flying-tile", children=self.fixed_canvas)
        self.add(self.flying_container)

        self.connect("button-press-event", self._on_background_click)

        self._animator = Animator(
            bezier_curve=(0.33, 1.0, 0.68, 1.0),  # ease-out-cubic-ish
            duration=0.3,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        self._animator.connect("notify::value", self._on_animator_value_changed)
        self._animator.connect("finished", self._on_animation_finished)

        self.curr_x = self.curr_y = 0.0
        self.curr_w = self.curr_h = 0.0
        self._anim_start = (0.0, 0.0, 0.0, 0.0)
        self._anim_target = (0.0, 0.0, 0.0, 0.0)
        self._anim_on_complete = None

        self.source_slot = None
        self.source_widget = None
        self.expanded_factory = None
        self.expanded_widget = None
        self._size_watch_handle = None
        self._pending_resize = None
        self.add_keybinding("Escape", lambda *_: self.dismiss())
        self.connect("focus-out-event", lambda *_: self.dismiss())

    def _on_background_click(self, _widget, event):
        if self.source_slot is None:
            return False
        if self._point_in_content(event.x, event.y):
            return False  # click landed on the popped widget itself
        self.dismiss()
        return True

    def _point_in_content(self, x, y):
        return (
            self.curr_x <= x <= self.curr_x + self.curr_w
            and self.curr_y <= y <= self.curr_y + self.curr_h
        )

    def _monitor_geometry_for(self, x, y):
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_point(int(x), int(y))
        if monitor is None:
            monitor = display.get_primary_monitor()
        return monitor.get_geometry()

    def pop_out(self, slot: PopSlot, target_size=(320, 200), expanded_factory=None):
        if self.source_slot is not None:
            return

        gdk_window = slot.get_window()
        success, origin_x, origin_y = gdk_window.get_origin()
        if IS_WAYLAND:
            success, x, y = self._get_absolute_position(slot)
            origin_x, origin_y = origin_x + x, origin_y + y

        if not success:
            return

        alloc = slot.get_allocation()
        start_x, start_y = origin_x + alloc.x, origin_y + alloc.y
        start_w, start_h = alloc.width, alloc.height

        geometry = self._monitor_geometry_for(start_x, start_y)
        self.screen_width = geometry.width
        self.screen_height = geometry.height

        self.source_slot = slot
        self.expanded_factory = expanded_factory
        self.orig_x, self.orig_y = start_x, start_y
        self.orig_w, self.orig_h = start_w, start_h

        GLib.idle_add(
            self._begin_flight, start_x, start_y, start_w, start_h, target_size
        )

    def _get_absolute_position(self, widget):
        """Compute widget's current absolute (x, y) screen position."""
        toplevel = widget.get_toplevel()
        win = toplevel.get_window()
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_window(win) or display.get_monitor(0)
        geo = monitor.get_geometry()

        # window (toplevel) position via anchors/margins, as before
        win_alloc = toplevel.get_allocation()
        win_w, win_h = win_alloc.width, win_alloc.height

        anchored_top = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.TOP)
        anchored_bottom = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.BOTTOM)
        anchored_left = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.LEFT)
        anchored_right = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.RIGHT)

        margin_top = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.TOP)
        margin_bottom = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.BOTTOM)
        margin_left = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.LEFT)
        margin_right = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.RIGHT)

        if anchored_left and not anchored_right:
            win_x = geo.x + margin_left
        elif anchored_right and not anchored_left:
            win_x = geo.x + geo.width - margin_right - win_w
        elif anchored_left and anchored_right:
            win_x = geo.x + margin_left
        else:
            win_x = geo.x + (geo.width - win_w) // 2

        if anchored_top and not anchored_bottom:
            win_y = geo.y + margin_top
        elif anchored_bottom and not anchored_top:
            win_y = geo.y + geo.height - margin_bottom - win_h
        elif anchored_top and anchored_bottom:
            win_y = geo.y + margin_top
        else:
            win_y = geo.y + (geo.height - win_h) // 2

        return True, win_x, win_y

    def _begin_flight(self, start_x, start_y, start_w, start_h, target_size) -> bool:
        self.source_widget = self.source_slot.release()
        self.content_stack.add_named(self.source_widget, "collapsed")
        self.content_stack.set_visible_child_name("collapsed")
        self.set_pass_through(False)
        self.flying_container.add_style_class("darken")

        target_w, target_h = target_size
        target_x = (self.screen_width - target_w) // 2
        target_y = (self.screen_height - target_h) // 2

        # Position content BEFORE mapping the window
        self.content_frame.set_size_request(int(start_w), int(start_h))
        self.fixed_canvas.move(self.content_frame, int(start_x), int(start_y))

        if not self.get_visible():
            self.set_visible(True)
        self.show_all()

        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)

        self._animate_to(
            start=(start_x, start_y, start_w, start_h),
            target=(target_x, target_y, target_w, target_h),
            on_complete=self._land,
        )
        return False

    def _land(self):
        if self.expanded_factory is not None:
            self.expanded_widget = self.expanded_factory()
            self.content_stack.add_named(self.expanded_widget, "expanded")
            self.content_stack.set_visible_child_name("expanded")
        self._watch_content_size(self.content_stack.get_visible_child())

        if hasattr(self.source_slot, "on_flight_landed"):
            self.source_slot.on_flight_landed()

    def _watch_content_size(self, widget):
        self._unwatch_content_size()
        handle = widget.connect("size-allocate", self._on_content_resized)
        self._size_watch_handle = (widget, handle)

    def _unwatch_content_size(self):
        if self._size_watch_handle is not None:
            widget_prev, handle = self._size_watch_handle
            widget_prev.disconnect(handle)
            self._size_watch_handle = None

    def _on_content_resized(self, widget, alloc):
        new_w, new_h = widget.get_preferred_width()[1], widget.get_preferred_height()[1]
        if (new_w, new_h) == (self.curr_w, self.curr_h):
            return

        if self._animator.playing:
            # Mid-flight (pop-in/pop-out): don't fight the current
            # animation, just remember the latest size and re-target
            # once it settles.
            self._pending_resize = (new_w, new_h)
            return

        self._retarget_to_size(new_w, new_h)

    def _retarget_to_size(self, new_w, new_h):
        target_x = (self.screen_width - new_w) // 2
        target_y = (self.screen_height - new_h) // 2
        self._animate_to(
            start=(self.curr_x, self.curr_y, self.curr_w, self.curr_h),
            target=(target_x, target_y, new_w, new_h),
        )

    def dismiss(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

        if self.source_slot is None:
            return

        def start_shrink():
            if hasattr(self.source_slot, "on_flight_begin_restored"):
                self.source_slot.on_flight_begin_restored()

            self.set_pass_through(True)
            self.flying_container.remove_style_class("darken")

            should_seek = (
                not self.source_slot.get_mapped()
            )  # fails when slot is in mid-transition

            if should_seek:
                self.add_style_class("fade-out")
                self._animate_to(
                    start=(self.curr_x, self.curr_y, self.curr_w, self.curr_h),
                    target=(self.curr_x, self.curr_y, 0, 0),
                    on_complete=self._finish_dismiss,
                )
            else:
                self._animate_to(
                    start=(self.curr_x, self.curr_y, self.curr_w, self.curr_h),
                    target=(self.orig_x, self.orig_y, self.orig_w, self.orig_h),
                    on_complete=self._finish_dismiss,
                )

        if self.content_stack.get_visible_child_name() == "expanded":
            self.content_stack.set_visible_child_name("collapsed")
            GLib.timeout_add(
                self.content_stack.get_transition_duration(),
                lambda: (start_shrink(), False)[1],
            )
        else:
            start_shrink()

    def _finish_dismiss(self):
        slot = self.source_slot
        self._unwatch_content_size()

        self.remove_style_class("fade-out")

        gdk_window = self.source_widget.get_window()
        # TODO: this shit doesn't work :(
        if gdk_window is not None:
            # Snapshot the flying widget's current appearance before we
            # tear its GdkWindow down for reparenting. This lets us paint
            # a stand-in in the slot's place during the unrealize/realize
            # gap.
            alloc = self.source_widget.get_allocation()
            surface = gdk_window.create_similar_surface(
                cairo.CONTENT_COLOR_ALPHA, alloc.width, alloc.height
            )
            cr = cairo.Context(surface)
            self.source_widget.draw(cr)

            ghost = Gtk.Image.new_from_surface(surface)
            ghost.set_size_request(alloc.width, alloc.height)
            slot.show_ghost(ghost)  # slot packs `ghost` while widget is mid-reparent

        if self.expanded_widget is not None:
            self.content_stack.remove(self.expanded_widget)
            self.expanded_widget = None
        self.content_stack.remove(self.source_widget)
        slot.restore(self.source_widget)  # swaps ghost out for the real widget
        self.hide()

        self.source_slot = None
        self.source_widget = None
        self.expanded_factory = None
        self._pending_resize = None

        # emit
        self.flight_restored(slot)

    def _animate_to(self, start, target, on_complete=None):
        self._anim_start = start
        self._anim_target = target
        self._anim_on_complete = on_complete
        self.curr_x, self.curr_y, self.curr_w, self.curr_h = start
        self._animator.stop()
        self._animator.play()

    def _on_animator_value_changed(self, _animator, _pspec):
        t = self._animator.value  # already eased into [0, 1]
        sx, sy, sw, sh = self._anim_start
        tx, ty, tw, th = self._anim_target

        self.curr_x = sx + (tx - sx) * t
        self.curr_y = sy + (ty - sy) * t
        self.curr_w = sw + (tw - sw) * t
        self.curr_h = sh + (th - sh) * t

        self.content_frame.set_size_request(int(self.curr_w), int(self.curr_h))
        self.fixed_canvas.move(self.content_frame, int(self.curr_x), int(self.curr_y))

    def _on_animation_finished(self, _animator):
        cb, self._anim_on_complete = self._anim_on_complete, None
        if cb:
            cb()
        # `finished` fires while we're still inside Animator.do_update_value,
        # which calls pause() right after - restarting the animator here
        # synchronously would have that pending pause() rip out the fresh
        # tick handler we just installed. Defer to the next mainloop turn.
        if self._pending_resize is not None:
            GLib.idle_add(self._apply_pending_resize)

    def _apply_pending_resize(self):
        if self._pending_resize is not None:
            new_w, new_h = self._pending_resize
            self._pending_resize = None
            self._retarget_to_size(new_w, new_h)
        return False

    def request_dismiss(self, slot):
        if self.source_slot is slot:
            self.dismiss()
