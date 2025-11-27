from typing import Tuple

from config.info import HOME_DIR
from utils.colors import get_css_variable, hex_to_rgb01

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Shape(Gtk.DrawingArea):
    """Base class for all shape widgets (provides color and sizing utilities)."""

    def __init__(self, size: Tuple[int, int] = (140, 140), dark: bool = False):
        super().__init__()
        self.set_size_request(*size)
        self.dark = dark
        self._override_color: Tuple[float, float, float] | None = None
        self.connect("draw", self.on_draw)
        self.show()

    def _get_color(self) -> Tuple[float, float, float]:
        """Return the current RGB color (override or from CSS variable)."""
        if self._override_color is not None:
            return self._override_color

        hex_color = get_css_variable(
            f"{HOME_DIR}/fabric/styles/colors.css",
            "--on-primary" if self.dark else "--primary",
        )
        return hex_to_rgb01(hex_color)

    def set_color(self, rgb: Tuple[float, float, float] | None, redraw: bool = True):
        """Override the shape color and optionally trigger a redraw."""
        self._override_color = rgb
        if redraw:
            self.queue_draw()

    def on_draw(self, widget, ctx):
        pass
