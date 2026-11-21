from config.info import ROOT_DIR
from utils.colors import get_css_variable, hex_to_rgb01

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Shape(Gtk.DrawingArea):
    def __init__(self, size: tuple[int, int] = (140, 140), dark: bool = False, override_color: tuple[float, float, float] | None = None):
        super().__init__()
        self.set_size_request(*size)
        self.dark = dark
        self._override_color: tuple[float, float, float] | None = override_color
        self.connect("draw", self.on_draw)
        self.show()

    def _get_color(self) -> tuple[float, float, float]:
        if self._override_color is not None:
            return self._override_color

        hex_color = get_css_variable(
            f"{ROOT_DIR}/styles/colors.css",
            "--on-primary" if self.dark else "--primary",
        )
        return hex_to_rgb01(hex_color)

    def set_color(self, rgb: tuple[float, float, float] | None, redraw: bool = True):
        self._override_color = rgb
        if redraw:
            self.queue_draw()

    def on_draw(self, widget, ctx):
        pass
