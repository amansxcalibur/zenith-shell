from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window

from loguru import logger

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gdk, Gtk

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
            child=Revealer(
                transition_duration=250,
                transition_type='crossfade',
                child=child)
        )
        # self.set_position(Gtk.WindowPosition.NONE)
        # self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        # self.set_decorated(False)
        # self.set_resizable(False)

        self.children=self.event_box

        self.is_hover_popup = False
        self.is_hover_widget = False
        self.pointing_widget = widget

        if not isinstance(self.pointing_widget, EventBox):
            logger.error('Popup target widget should be an EventBox instance')

        self.delay_ref = None # this is a temp patch cuz popup window allocation issues

        self.pointing_widget.connect("enter-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=True))
        self.pointing_widget.connect("leave-notify-event", lambda x, y: self.set_is_hover_widget(event=y, state=False))
        self.event_box.connect("enter-notify-event", lambda x, y: self.set_is_hover_popup(event=y, state=True))
        self.event_box.connect("leave-notify-event", lambda x, y: self.set_is_hover_popup(event=y, state=False))

        self.connect("realize", lambda *_: self.place_popup())
        self.connect("configure-event", lambda *_: self.place_popup())

        # positioning events
        self.pointing_widget.connect("size-allocate", lambda *_: (self.place_popup))
        self.connect("size-allocate", self.place_popup)

    def do_draw(self, cr):
        self.place_popup()
        return Window.do_draw(self, cr)

    # def do_size_allocate(self, alloc):
    #     Window.do_size_allocate(self, alloc)
    #     self.set_position(Gtk.WindowPosition.NONE)
    #     self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
    #     self.set_decorated(False)
    #     self.set_resizable(False)
    #     # GLib.idle_add(lambda:self.place_popup())
    #     # return super().do_size_allocate(alloc)
    #     self.place_popup()
    
    def place_popup(self, *_):
        widget_alloc = self.pointing_widget.get_allocation()
        win_alloc = self.get_allocation()
        
        try:
            _, root_x, root_y = self.pointing_widget.get_window().get_origin()
        
            abs_x = root_x + widget_alloc.x - (win_alloc.width / 2 - widget_alloc.width / 2)
            abs_y = root_y + widget_alloc.y - win_alloc.height - 3

            # print(abs_x, abs_y)
            self.get_window().move(abs_x, abs_y)
            # self.visible = True
        except Exception as e:
            logger.error(f"Failed to place popup window: {e}")


    def set_is_hover_popup(self, event, state):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self.is_hover_popup = state
        self.handle_window_visibility()

    def set_is_hover_widget(self, event, state):
        logger.debug('here')
        self.is_hover_widget = state
        self.handle_window_visibility()

    def handle_window_visibility(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            if self.delay_ref != None:
                GLib.source_remove(self.delay_ref)
            self.delay_ref = GLib.timeout_add(250, self._check_and_hide)
        else:
            self.set_visible(True)
            self.event_box.get_children()[0].reveal()

    def _check_and_hide(self):
        if not self.is_hover_widget and not self.is_hover_popup:
            self.event_box.get_children()[0].unreveal()
            GLib.timeout_add(300, lambda:self.set_visible(False))
        return False
    

