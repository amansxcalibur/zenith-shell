import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
import cairo
import math

class OverlayWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_title("Pass-through Overlay")
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.SPLASHSCREEN)
        self.set_keep_above(True)
        self.set_default_size(400, 300)
        self.connect("destroy", Gtk.main_quit)
        self.connect("realize", self.on_realize)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and self.is_composited():
            self.set_visual(visual)

        drawing_area = Gtk.DrawingArea()
        drawing_area.connect("draw", self.on_draw)
        self.add(drawing_area)

    def on_realize(self, widget):
        gdk_window = self.get_window()
        print(type(gdk_window))  # Should be <class 'gi.repository.Gdk.X11Window'>
        empty_region = cairo.Region()
        gdk_window.set_input_region(empty_region)

    def on_draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()

        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(1, 0, 0, 0.4)  # Semi-transparent red
        cr.arc(400 / 2, 300 / 2, 300 / 4, 0, 2 * math.pi)
        cr.fill()

win = OverlayWindow()
win.show_all()
Gtk.main()
