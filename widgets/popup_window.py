from fabric.widgets.eventbox import EventBox
from fabric.widgets.x11 import X11Window as Window

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gdk

class PopupWindow(Window):
    def __init__(self, widget, child, **kwargs):        
        super().__init__(
            type_hint="normal",
            visible=False,
            all_visible=False,
            **kwargs
        )
        self.event_box = EventBox(
            orientation="h",
            spacing=0,
            h_expand=True,
            v_expand=True,
            child=child
        )
        self.children=self.event_box

        self.is_hover_popup = False
        self.is_hover_widget = False
        self.pointing_widget = widget

        self.delay_ref = None # this is a temp patch cuz popup window allocation issues

        # visibility events
        if hasattr(self.pointing_widget, 'event_box'):
            self.pointing_widget.event_box.connect("enter-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=True))
            self.pointing_widget.event_box.connect("leave-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=False))
        else:
            self.pointing_widget.connect("enter-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=True))
            self.pointing_widget.connect("leave-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=False))
        self.event_box.connect("enter-notify-event", lambda x, y: self.set_is_hover_popup(event=y, state=True))
        self.event_box.connect("leave-notify-event", lambda x, y: self.set_is_hover_popup(event=y, state=False))

        # positioning events
        self.pointing_widget.connect("size-allocate", self.place_popup)
        self.connect("size-allocate", self.place_popup)

    def place_popup(self, *_):
        # relative to parent
        widget_alloc = self.pointing_widget.get_allocation()
        win_alloc = self.get_allocation()

        _, root_x, root_y = self.pointing_widget.get_window().get_origin()

        abs_x = root_x + widget_alloc.x - (win_alloc.width / 2 - widget_alloc.width / 2)
        abs_y = root_y + widget_alloc.y - win_alloc.height - 3

        self.move(abs_x, abs_y)
        self.visible = True

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
            if self.delay_ref != None:
                GLib.source_remove(self.delay_ref)
            self.delay_ref = GLib.timeout_add(250, self._check_and_hide)
        else:
            self.set_visible(True)

    def _check_and_hide(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            self.set_visible(False)
        return False
    

