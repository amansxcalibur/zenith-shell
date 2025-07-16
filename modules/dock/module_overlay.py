import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal


class HoverOverlay(EventBox, Service):
    @Signal
    def hole_index(self, id: int) -> None: ...

    def __init__(self, target_box: Gtk.Widget, hole_box: Gtk.Widget, layout_manager, id: int, edge_flag=False, **kwargs):
        super().__init__(
            name="hover-overlay",
            events=["enter-notify", "leave-notify"],
            visible_window=False,
        )

        self._id = id
        self._target = target_box
        self._hole = hole_box
        self._edge_flag = edge_flag
        self._layout_manager = layout_manager
        self.width = 0
        self.is_currently_hovered = False

        import time
        self.last_hover_time = time.monotonic()

        self.add(self._target)

        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

        self._target.connect("size-allocate", self.on_target_resize)
        self._resize_timeout = None

    def on_hover(self, widget, event):
        print("setting hover True")
        self.is_currently_hovered = True
        self._target.set_style("" \
        "padding-bottom:3px; padding-left:3px; padding-right:3px; " \
        "transition: padding-bottom 0.1s cubic-bezier(0.5, 0.25, 0, 1)"
        )
        self.hole_index(self._id)

    def on_unhover(self, widget, event):
        if event.detail == Gdk.NotifyType.INFERIOR: # hovering to a child widget, don't unhover
            return
        self.is_currently_hovered = False
        self._target.set_style("" \
        "padding-left:3px; padding-right:3px; " \
        "transition: padding-bottom 0.1s cubic-bezier(0.5, 0.25, 0, 1)" \
        )
        self._hole.set_style("min-width:0px;")
        self.hole_index(-1)

    def on_target_resize(self, widget, allocation):
        new_width = allocation.width
        if self._edge_flag:
            new_width -= 20

        if self.width != new_width:
            print(widget.children[0].get_name(), " changing:", new_width)
            self.width = new_width

            if self._resize_timeout:
                GLib.source_remove(self._resize_timeout)
            
            self._resize_timeout = GLib.timeout_add(50, self._emit_hover_signal)

    def _emit_hover_signal(self):
        print("emitting signal, is hovered?", self.is_currently_hovered)
        if self.is_currently_hovered:
            self.hole_index(self._id)
        self._resize_timeout = None
        return False



class HolePlaceholder(Box):
    def __init__(self, target, edge_flag, **kwargs):
        super().__init__(name="hole-placeholder-box")
        self._edge_flag = edge_flag
        self._target = target
        self.width = self.get_allocation().width # width handling done in HoverOverlay funnily enough