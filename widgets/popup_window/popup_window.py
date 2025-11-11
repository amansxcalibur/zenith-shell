from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window

from loguru import logger

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gdk


class PopupWindow(Window):
    def __init__(
        self,
        pointing_widget,
        child,
        transition_duration=250,
        transition_type="crossfade",
        **kwargs,
    ):
        super().__init__(type_hint="normal", visible=False, all_visible=False, **kwargs)

        if not isinstance(pointing_widget, EventBox):
            logger.error(
                "The widget PopupWindow is pointing to must be an EventBox instance"
            )
            # raise TypeError("pointing_widget must be an EventBox")

        self.revealer = Revealer(
            transition_duration=transition_duration,
            transition_type=transition_type,
            child=child,
        )

        self.event_box = EventBox(
            orientation="h",
            spacing=0,
            h_expand=True,
            v_expand=True,
            child=self.revealer,
        )

        self.children = self.event_box

        # Disconnect the geometry enforcement hook on window size-reallocate
        # in source to remove jitter when children props change.
        if hasattr(self, "_size_allocate_hook") and self._size_allocate_hook:
            try:
                self.handler_disconnect(self._size_allocate_hook)
                self._size_allocate_hook = None
            except Exception as e:
                logger.debug(f"Could not disconnect size allocate hook: {e}")

        self.is_hover_popup = False
        self.is_hover_widget = False
        self.pointing_widget = pointing_widget

        # this is a temp patch cuz popup window allocation issues
        self.unhover_delay_ref = None
        self.hide_delay_ref = None

        self.pointing_widget.connect(
            "enter-notify-event",
            lambda x, y: self.set_is_hover_widget(event=y, state=True),
        )
        self.pointing_widget.connect(
            "leave-notify-event",
            lambda x, y: self.set_is_hover_widget(event=y, state=False),
        )
        self.event_box.connect(
            "enter-notify-event",
            lambda x, y: self.set_is_hover_popup(event=y, state=True),
        )
        self.event_box.connect(
            "leave-notify-event",
            lambda x, y: self.set_is_hover_popup(event=y, state=False),
        )

        # positioning events
        self.pointing_widget.connect("size-allocate", lambda *_: (self.place_popup))

    def do_draw(self, cr):
        self.place_popup()
        return Window.do_draw(self, cr)

    def place_popup(self, *_):
        widget_alloc = self.pointing_widget.get_allocation()
        win_alloc = self.get_allocation()

        try:
            _, root_x, root_y = self.pointing_widget.get_window().get_origin()

            abs_x = (
                root_x + widget_alloc.x - (win_alloc.width / 2 - widget_alloc.width / 2)
            )
            abs_y = root_y + widget_alloc.y - win_alloc.height - 3

            # print(abs_x, abs_y)
            win = self.get_window()
            if win is not None:
                win.move(abs_x, abs_y)
            # self.visible = True
        except Exception as e:
            logger.error(f"Failed to place popup window: {e}")

    def set_is_hover_popup(self, event, state):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self.is_hover_popup = state
        self.handle_window_visibility()

    def set_is_hover_widget(self, event, state):
        self.is_hover_widget = state
        self.handle_window_visibility()

    def handle_window_visibility(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            if self.unhover_delay_ref is not None:
                GLib.source_remove(self.unhover_delay_ref)
            self.unhover_delay_ref = GLib.timeout_add(250, self._check_and_hide)
        else:
            if self.hide_delay_ref is not None:
                GLib.source_remove(self.hide_delay_ref)
            self.set_visible(True)
            self.revealer.reveal()

    def _check_and_hide(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            self.revealer.unreveal()
            self.hide_delay_ref = GLib.timeout_add(300, lambda: self.set_visible(False))
        return False
