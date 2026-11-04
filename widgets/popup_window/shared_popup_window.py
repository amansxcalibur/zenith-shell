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
from utils.helpers import get_absolute_wayland_widget_position
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

        # hover state tracking
        self.is_hover_popup = False
        self.is_hover_widget = False

        # timer references
        self.unhover_delay_ref = None
        self.hide_delay_ref = None

        # widget-popup mapping
        self.child_pointing_widget_dict = {}

        self._animations_enabled = (
            power_profiles_service.active_profile != "power-saver"
        )
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

    def _on_power_profile_changed(self, *_):
        self._animations_enabled = (
            power_profiles_service.active_profile != "power-saver"
        )
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

            was_already_visible = self.get_visible()

            def _set_position():
                along = self._calculate_popup_position()
                if along is not None:
                    if was_already_visible and self._animations_enabled:
                        self.animate_to_position(along)
                    else:
                        self.place_popup(along)
                return False

            GLib.idle_add(_set_position)

        self._handle_window_visibility()

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
        if not IS_WAYLAND and getattr(self, "pointing_widget", None) and self.get_mapped():
            try:
                _, nat = self.get_preferred_size()
                win = self.get_window()
                # compare against what we last sent; the GdkWindow size lags
                # until ConfigureNotify, which would resend the same request
                if win and (nat.width, nat.height) != self._current_size():
                    x, y = self._x11_position(
                        self.target_along, nat.width, nat.height
                    )
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
        return True
