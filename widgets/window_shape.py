import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


def can_be_transparent(window: Gtk.Window) -> bool:
    # a compositor alone isn't enough, without a 32 bit visual there's no alpha
    return window.is_composited() and window.get_visual().get_depth() == 32


def shape_window(window: Gtk.Window, region: cairo.Region):
    # no alpha: the empty part of the window paints black, so cut the window down to what's drawn
    window.shape_combine_region(None if can_be_transparent(window) else region)
