import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import sys
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.x11 import X11Window as Window
from fabric import Application
from fabric.utils import get_relative_path

class WigglyWidget(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.phase = 0
        # self.set_size_request(600, 100)
        self.connect("draw", self.on_draw)
        GLib.timeout_add(16, self.update)  # 60 FPS

    def update(self):
        self.phase += 0.2
        self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_y = height / 2
        amplitude = 2
        frequency = 0.3

        cr.set_source_rgb(0.2, 0.8, 0.2)  # Greenish
        cr.set_line_width(2)

        cr.move_to(0, center_y)
        for x in range(width):
            y = center_y + amplitude * math.sin((x * frequency) + self.phase)
            cr.line_to(x, y)

        cr.stroke()


class WigglyFabricWindow(Window):
    def __init__(self):
        super().__init__(
            name="wiggle-fabric-window",
            geometry=(600, 100),
            visible=True,
            layer="top",
            type_hint="menu"
        )

        wiggly = WigglyWidget()

        # Wrap Gtk.DrawingArea in a Gtk.Box that expands
        gtk_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        gtk_wrapper.set_hexpand(True)
        gtk_wrapper.set_vexpand(True)
        gtk_wrapper.set_halign(Gtk.Align.FILL)
        gtk_wrapper.set_valign(Gtk.Align.FILL)
        gtk_wrapper.add(wiggly)

        self.children = CenterBox(
            name="container",
            h_align="fill",
            v_align="fill",
            # orientation='v',
            center_children=[
                # Box(name="test"),
                # Box(name="test"),
                gtk_wrapper
            ]
        )
# class WigglyWindow(Gtk.Window):
#     def __init__(self):
#         super().__init__(title="Squiggly Line")
#         self.set_default_size(600, 100)
#         self.set_resizable(False)
#         self.set_position(Gtk.WindowPosition.CENTER)

#         self.add(WigglyWidget())

#         self.connect("destroy", Gtk.main_quit)

# if __name__ == "__main__":
#     win = WigglyWindow()
#     win.show_all()
#     Gtk.main()

if __name__ == "__main__":
    win = WigglyFabricWindow()
    win.show_all()
    app = Application("wiggly", win)
    app.set_stylesheet_from_file(get_relative_path("./styles/wiggle.css"))   
    app.run()
