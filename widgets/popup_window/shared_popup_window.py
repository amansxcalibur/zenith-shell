from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window

from services.animator import Animator

from loguru import logger

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gdk


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
        self.should_animate = False

        # animation position tracking
        self.current_x = 0
        self.current_y = 0
        self.target_x = 0
        self.target_y = 0

        # hover state tracking
        self.is_hover_popup = False
        self.is_hover_widget = False

        # timer references
        self.unhover_delay_ref = None
        self.hide_delay_ref = None

        # widget mapping
        self.child_pointing_widget_dict = {}

        self._initialize_animators()
        self._initialize_ui(transition_duration, transition_type)

        # Disconnect the geometry enforcement hook
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
            lambda x, y: self.set_is_hover_popup(event=y, state=True),
        )
        self.event_box.connect(
            "leave-notify-event",
            lambda x, y: self.set_is_hover_popup(event=y, state=False),
        )

        # self.connect("configure-event", self.on_window_move)

    def _initialize_animators(self):
        self.animator_x = Animator(
            bezier_curve=self.ANIMATION_BEZIER,
            duration=self.ANIMATION_DURATION,
            min_value=0,
            max_value=0,
            tick_widget=self,
            notify_value=lambda p, *_: self._update_x_position(p.value),
        )
        # self.animator_y = Animator(
        #     bezier_curve=(0.15, 0.88, 0.68, 0.95),
        #     duration=0.1,
        #     min_value=0,
        #     max_value=0,
        #     tick_widget=self,
        #     notify_value=lambda p, *_: self._update_y_position(p.value),
        # )

    def _initialize_ui(self, transition_duration, transition_type):
        self.stack = Stack(
            transition_type=transition_type,
            transition_duration=transition_duration,
            style="background-color:rgba(0,0,0,0.1); padding:5px; border-radius:20px",
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.revealer = Revealer(
            transition_duration=transition_duration,
            transition_type=transition_type,
            child=self.stack,
        )

        self.event_box = EventBox(
            orientation="h",
            spacing=0,
            child=self.revealer,
        )

        self.children = Box(children=self.event_box)

    def _update_x_position(self, x_value):
        self.current_x = x_value
        self._apply_position()

    def _update_y_position(self, y_value):
        self.current_y = y_value
        self._apply_position()

    def _apply_position(self):
        win = self.get_window()
        if win is not None:
            win.move(int(self.current_x), int(self.current_y))

    def animate_to_position(self, target_x, target_y):
        win = self.get_window()
        if win is not None:
            _, current_x, current_y = win.get_origin()
            self.current_x = current_x
            self.current_y = current_y

        # set up animators
        self.animator_x.pause()
        self.animator_x.min_value = self.current_x
        self.animator_x.max_value = target_x
        self.animator_x.value = self.current_x

        self.current_y = target_y

        # self.animator_y.pause()
        # self.animator_y.min_value = self.current_y
        # self.animator_y.max_value = target_y
        # self.animator_y.value = self.current_y

        self.animator_x.play()
        # self.animator_y.play()

    # def on_window_move(self, widget, event):
    #     print(f"Window moved to ({event.x}, {event.y}), size = {event.width}x{event.height}")

    def add_child(self, pointing_widget, child):
        if not isinstance(pointing_widget, EventBox):
            logger.error(
                "The widget PopupWindow is pointing to must be an EventBox instance"
            )

        pointing_widget.connect(
            "enter-notify-event",
            lambda x, y: self.set_is_hover_widget(source=x, event=y, state=True),
        )
        pointing_widget.connect(
            "leave-notify-event",
            lambda x, y: self.set_is_hover_widget(source=x, event=y, state=False),
        )

        self.child_pointing_widget_dict[pointing_widget] = child
        self.stack.add_named(child, child.get_name())

    def do_draw(self, cr):
        self.place_popup()
        return Window.do_draw(self, cr)

    def _calculate_popup_position(self):
        if not self.pointing_widget:
            return None, None

        widget_alloc = self.pointing_widget.get_allocation()
        win_alloc = self.get_allocation()

        try:
            _, root_x, root_y = self.pointing_widget.get_window().get_origin()

            # center horizontally, place above the widget
            target_x = (
                root_x + widget_alloc.x - (win_alloc.width / 2 - widget_alloc.width / 2)
            )
            target_y = root_y + widget_alloc.y - win_alloc.height - self.POPUP_OFFSET

            return target_x, target_y

        except Exception as e:
            logger.error(f"Failed to calculate popup position: {e}")
            return None, None

    def place_popup(self, *_):
        target_x, target_y = self._calculate_popup_position()

        if target_x is None:
            return

        if self.should_animate:
            self.animate_to_position(target_x, target_y)
        else:
            self._update_x_position(target_x)
            self._update_y_position(target_y)
            self._apply_position()

    def set_is_hover_popup(self, event, state):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return

        self.is_hover_popup = state
        self.handle_window_visibility()

    def set_is_hover_widget(self, source, event, state):
        self.is_hover_widget = state
        self.pointing_widget = source

        next_visible_child = self.child_pointing_widget_dict[source]
        self.stack.set_visible_child(next_visible_child)

        self.handle_window_visibility()

    def _cancel_pending_timers(self):
        if self.hide_delay_ref is not None:
            GLib.source_remove(self.hide_delay_ref)
            self.hide_delay_ref = None

        if self.unhover_delay_ref is not None:
            GLib.source_remove(self.unhover_delay_ref)
            self.unhover_delay_ref = None

    def handle_window_visibility(self):
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

            # enable animation if already visible
            was_visible = self.get_visible()
            self.should_animate = was_visible

            self.set_visible(True)
            self.place_popup()
            self.revealer.reveal()

    def _check_and_hide(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            self.revealer.unreveal()
            self.hide_delay_ref = GLib.timeout_add(
                self.HIDE_DELAY_MS, lambda: self.set_visible(False)
            )
        return False
