import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk

from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.overlay import Overlay
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from utils.helpers import toggle_class
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal


class HoverOverlay(EventBox, Service):
    @Signal
    def hole_index(self, id: int) -> None: ...

    def __init__(self, target_box: Gtk.Widget, hole_box: Gtk.Widget, id: int, **kwargs):
        super().__init__(
            events=["enter-notify", "leave-notify"],
            visible_window=False,
        )

        self._id = id
        self._target = target_box
        self._hole = hole_box
        self.width = 0
        import time
        self.last_hover_time = time.monotonic()

        self.add(self._target)
        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

    def on_hover(self, widget, event):
        # print("Hover in", self._id)
        if self.width == 0:
            self.width = self._target.get_allocated_width()

        self.hole_index(self._id)
        # self._hole.set_style(
        #     "min-width:0px; transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        # )

    def on_unhover(self, widget, event):
        # print("Hover out", self._id)
        self.hole_index(-1)
        # self._hole.set_style(
        #     f"min-width:{self.width}px; transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        # ),


class HolePlaceholder(Box):
    def __init__(self, target, edge_flag, **kwargs):
        super().__init__(name="hole-placeholder-box")
        self._edge_flag = edge_flag
        self._target = target
        self._target.connect("size-allocate", self.on_size_allocate)
        self.width = self.get_allocation().width

    def on_size_allocate(self, widget, allocation):
        width = allocation.width
        if self._edge_flag:
            print(f"change {width}")
            width-=20
        if self.width != width:
            self.width = width
            self.set_style(f"min-width:{width}px;")
            print(f"Hole updated width: {width}")
