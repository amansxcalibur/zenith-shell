import re
from functools import lru_cache

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Gtk, Gdk, Rsvg  # type: ignore

from config.info import ROOT_DIR

LOGO_PATH = ROOT_DIR / "svg" / "zenith-logo.svg"


def _css_color(rgba: Gdk.RGBA) -> str:
    r, g, b = (round(channel * 255) for channel in (rgba.red, rgba.green, rgba.blue))
    return f"rgba({r},{g},{b},{rgba.alpha:.3f})"


@lru_cache(maxsize=8)
def _themed_handle(background: str, foreground: str) -> Rsvg.Handle:
    style = (
        f"<style>.zenith-bg{{fill:{background}}}.zenith-fg{{fill:{foreground}}}"
        f".zenith-stroke{{stroke:{foreground}}}</style>"
    )
    svg = re.sub(
        r"<style>.*?</style>", style, LOGO_PATH.read_text(), count=1, flags=re.DOTALL
    )
    return Rsvg.Handle.new_from_data(svg.encode())


class ZenithLogo(Gtk.DrawingArea):
    def __init__(self, size: int = 128, **kwargs):
        super().__init__(name="zenith-logo", **kwargs)
        self.set_size_request(size, size)
        self.connect("style-updated", lambda *_: self.queue_draw())

    def do_draw(self, cr: cairo.Context):
        context = self.get_style_context()
        state = context.get_state()
        handle = _themed_handle(
            _css_color(context.get_property("background-color", state)),
            _css_color(context.get_color(state)),
        )

        # the largest centred square
        width, height = self.get_allocated_width(), self.get_allocated_height()
        side = min(width, height)
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y = (width - side) / 2, (height - side) / 2
        viewport.width = viewport.height = side
        handle.render_document(cr, viewport)
        return False
