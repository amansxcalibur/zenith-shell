from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window

from widgets.clipping_box import ClippingBox
from services.animator import Animator

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gdk, Gtk


class SharedPopupWindow(Window):
    _instance = None
    _initialized = False

    # constants
    DEFAULT_TRANSITION_DURATION = 250
    DEFAULT_TRANSITION_TYPE = "crossfade"
    UNHOVER_DELAY_MS = 250
    HIDE_DELAY_MS = 300
    POPUP_OFFSET = 3  # pixels above the widget

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

        super().__init__(
            layer="top",
            type_hint="normal",
            visible=False,
            all_visible=False,
            **kwargs,
        )
        self._initialized = True

        self.pointing_widget = None
        self.pointing_widget_size_alloc_hook = None

        # animation position tracking
        self.target_x = 0
        self.target_y = 0

        # hover state tracking
        self.is_hover_popup = False
        self.is_hover_widget = False

        # timer references
        self.unhover_delay_ref = None
        self.hide_delay_ref = None

        # widget-popup mapping
        self.child_pointing_widget_dict = {}

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
        # self.connect("configure-event", self.on_window_move)

    # def on_window_move(self, widget, event):
    #     print(
    #         f"Window moved to ({event.x}, {event.y}), size = {event.width}x{event.height}"
    #     )
    #     ...

    def _initialize_ui(self, transition_duration, transition_type):
        self.stack = Stack(
            transition_type=transition_type,
            transition_duration=transition_duration,
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.revealer = Revealer(
            transition_duration=transition_duration,
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
        self.animator_x = Animator(
            bezier_curve=self.ANIMATION_BEZIER,
            duration=self.ANIMATION_DURATION,
            tick_widget=self,
            notify_value=self._on_animator_x_tick,
        )

    def _on_animator_x_tick(self, p, *_):
        self.target_x = p.value
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
                x, y = self._calculate_popup_position()
                if x is not None:
                    if was_already_visible:
                        self.animate_to_position(x, y)
                    else:
                        # moves coords calculated using widget preferred height/width
                        _, popup_widget_height = (
                            next_visible_child.get_preferred_height()
                        )
                        win = self.get_window()
                        if win:
                            win.move(
                                int(self._clamp_x(x)),
                                int(self._get_target_baseline() - popup_widget_height),
                            )
                        self.target_x = x
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

        x, y = self._calculate_popup_position()

        if self.animator_x.playing:
            self.animate_to_position(x, y)  # pauses, updates and plays
            return
        else:
            self.place_popup(x)

    def _calculate_popup_position(self):
        if not self.pointing_widget:
            return None, None

        widget_alloc = self.pointing_widget.get_allocation()
        win_alloc = self.get_allocation()
        _, popup_widget_alloc = self.child_pointing_widget_dict[
            self.pointing_widget
        ].get_preferred_width()

        try:
            _, root_x, root_y = self.pointing_widget.get_window().get_origin()

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
            target_y = root_y + widget_alloc.y - win_alloc.height - self.POPUP_OFFSET

            return target_x, target_y

        except Exception as e:
            logger.error(f"Failed to calculate popup position: {e}")
            return None, None

    def _get_target_baseline(self):
        _, _, pointing_widget_root_y = self.pointing_widget.get_window().get_origin()
        return (
            pointing_widget_root_y
            + self.pointing_widget.get_allocation().y
            - self.POPUP_OFFSET
        )

    def _clamp_x(self, x: int, width: int = None) -> int:
        screen = self.get_screen()
        if screen is None:
            return x
        w = width if width is not None else self.get_allocation().width
        return max(self.POPUP_OFFSET, min(x, screen.get_width() - w))

    def _clamp_y(self, y: int, height: int = None) -> int:
        screen = self.get_screen()
        if screen is None:
            return y
        h = height if height is not None else self.get_allocation().height
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
            self.animator_x.pause()

            def _do_hide():
                self.set_visible(False)
                self.hide_delay_ref = None
                return False

            self.hide_delay_ref = GLib.timeout_add(self.HIDE_DELAY_MS, _do_hide)

        self.unhover_delay_ref = None
        return False

    def animate_to_position(self, target_x, target_y):
        _, start_x, _ = self.get_window().get_origin()
        self.animator_x.pause()
        self.animator_x.handler_block_by_func(self._on_animator_x_tick)
        self.animator_x.min_value = start_x
        self.animator_x.max_value = self._clamp_x(
            target_x,
            width=self.child_pointing_widget_dict[
                self.pointing_widget
            ].get_preferred_width()[1],
        )
        self.animator_x.value = start_x
        self.animator_x.handler_unblock_by_func(self._on_animator_x_tick)
        self.target_y = self._clamp_y(target_y)
        self.animator_x.play()

    def place_popup(self, override_x: int = None):
        if override_x is None:
            override_x = self.target_x
        else:
            self.target_x = override_x

        win = self.get_window()
        if win:
            win.move(
                int(self._clamp_x(override_x)),
                int(self._get_target_baseline() - self.get_allocation().height),
            )

    def do_size_allocate(self, alloc):
        # uses fresh allocation to move window before it extends below baseline
        if self.pointing_widget and self.get_mapped():
            try:
                win = self.get_window()
                if win:
                    win.move(
                        int(self._clamp_x(self.target_x)),
                        int(self._get_target_baseline() - alloc.height),
                    )

            except Exception as e:
                logger.error(f"do_size_allocate Y position failed: {e}")

        Gtk.Window.do_size_allocate(self, alloc)
