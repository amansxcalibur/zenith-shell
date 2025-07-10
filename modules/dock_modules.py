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


class DockModuleWrapper(Window):
    def __init__(self, widget, target_widget, **kwargs):
        super().__init__(
            name="docker-wrapper",
            type_hint="dialog",  # ensures no taskbar / border
            visible=True,
            all_visible=True,
            decorated=False,
            resizable=False,
            **kwargs,
        )
        # widget.set_name("docker-widget")  # for styling
        self.children = widget
        widget.add_style_class("dock-widget")

        pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        pill_size_group.add_widget(widget)
        pill_size_group.add_widget(target_widget)

        self.target_widget = target_widget
        self.dock_widget = widget
        self.set_app_paintable(True)

        # Initial positioning
        # GLib.idle_add(self.move_relative_to_target)

        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

        # self.move_relative_to_target(dy=-10)
        self.count = 7

    #     self._draw_handler_id = self.connect("draw", self.on_draw)

    # def on_draw(self, widget, cr):
    #     if self.count == 0:
    #         self.disconnect(self._draw_handler_id)
    #         return False  # stop drawing

    #     self.move_relative_to_target(dy=0)
    #     self.count -= 1
    #     print("i am called")
    #     return False

    def on_hover(self, *_):
        self.dock_widget.add_style_class("hoverer")
        if self.count > 0:
            self.move_relative_to_target(dy=-10)
            # return False  # stop drawing
        self.count -= 1

    def on_unhover(self, *_):
        self.dock_widget.remove_style_class("hoverer")
        if self.count > -1:
            self.move_relative_to_target(dy=0)
            # return False  # stop drawing
        self.count -= 1

    def move_relative_to_target(self, dx=0, dy=0):
        if not self.target_widget.get_window():
            return False

        # Get screen coordinates of target_widget
        window = self.target_widget.get_window()
        origin = window.get_origin()
        alloc = self.target_widget.get_allocation()

        x = origin.x + alloc.x + dx
        y = origin.y + alloc.y + dy

        print(x, y, "here are the target coordinates", self.count)

        self.move(x, y)
        return False  # Only run once in idle_add


class DockModuleOverlay(EventBox, Service):

    @Signal
    def hole_index(self, id: int) -> None: ...

    def __init__(self, overlays, id: int, **kwargs):
        super().__init__(
            events=["enter-notify", "leave-notify"],
        )

        self._id = id

        self._overlays = CenterBox(
            center_children=overlays,
            style="" "padding-left:3px;" "padding-right:3px;" "padding-bottom:3px;",
        )
        self.child = self.build_child()

        self.overlay = Overlay(child=self.child, overlays=self._overlays, **kwargs)

        self.add(self.overlay)

        # self.child.connect("size-allocate", self.on_size_allocate)

        # self.starter_box.set_style("border-radius:30px;")

        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

    def build_child(self):
        self.hole = Box(
            name="hori",
        )
        self.starter_box = Box(name="start", h_expand=True)
        self.ender_box = Box(name="end", h_expand=True)
        self._box = Box(
            name="dock-place",
            children=[
                self.starter_box,
                Box(
                    h_expand=True,
                    style="",
                    orientation="v",
                    children=[
                        self.hole,
                        Box(v_expand=True, style="background-color:black"),
                    ],
                ),
                self.ender_box,
            ],
            style="min-height:40px;",
        )

        # Optional: synchronize sizes
        if self._overlays:
            print("setting size grp")
            pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
            pill_size_group.add_widget(self._overlays)
            pill_size_group.add_widget(self._box)

        return self._box

    def on_hover(self, widget, event):
        print("Hover in")
        self.hole_index(self._id)
        width = widget.get_allocated_width()
        GLib.timeout_add(
            100,
            lambda: self.starter_box.set_style(
                "margin-top:30px;" \
                "transition: margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            ),
        )
        GLib.timeout_add(
            100,
            lambda: self.ender_box.set_style(
                "margin-top:30px;" \
                "transition: margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            ),
        )
        self.hole.set_style(
            "min-height:40px; "
            f"min-width:{width}px;"
            "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        )

        toggle_class(self.hole, "contractor", "expander")
        # toggle_class(self.starter_box, "contractor", "expander")
        # toggle_class(self.ender_box, "contractor", "expander")

    def on_unhover(self, widget, event):
        print("Hover out", self._id)
        # self.hole.remove_style_class("expander")
        self.hole_index(-2)  # to avoid i+1 going to 0
        GLib.timeout_add(
            125,
            lambda: self.hole.set_style(
                "min-height:0px;"
                "min-width:0px;"
                "margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1), min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            ),
        )
        
        # GLib.timeout_add(0, lambda m=self.starter_box: m.set_style("margin-top:30px;"))
        # GLib.timeout_add(100, lambda m=self.starter_box: m.set_style("margin-top:30px;"))
        # self.hole_index(-2)  # to avoid i+1 going to 0

        # toggle_class(self.starter_box, "expander", "contractor")
        # toggle_class(self.ender_box, "expander", "contractor")


# def on_size_allocate(self, widget, allocation):
#     width = allocation.width
#     height = allocation.height
#     print(f"Child width: {width}, height: {height}")
