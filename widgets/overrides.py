import cairo
from loguru import logger

from fabric.widgets.x11 import X11Window
from fabric.widgets.svg import Svg as FabricSvg

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import GObject, Rsvg, Gtk  # type: ignore


def enable_tooltip_transparency():
    """
    Gives GTK's tooltip window an alpha channel, so its rounded corners aren't
    black. GTK only does this itself if the window manager supports
    `_GTK_FRAME_EXTENTS`, which i3 doesn't.

    This should be called before the first tooltip is shown: the window can't change
    its visual once realized. GTK creates it on the first hover over a widget with a
    tooltip, just before asking that widget for the tooltip's contents.
    """

    def on_query_tooltip(*_):
        for window in Gtk.Window.list_toplevels():
            if type(window).__name__ == "GtkTooltipWindow":
                visual = window.get_screen().get_rgba_visual()
                if visual is not None:
                    window.set_visual(visual)
                return False  # done, remove this hook
        return True

    GObject.add_emission_hook(Gtk.Widget, "query-tooltip", on_query_tooltip)


class PatchedX11Window(X11Window):
    """
    Subclass that patches the `pass-through` behavior when
    `Gtk.StyleContext` uses `* { all: unset }`.
    """

    # bypass fabric's Window.do_size_allocate implementation
    def do_size_allocate(self, alloc):
        Gtk.Window.do_size_allocate(self, alloc)  # type: ignore

    def do_map_event(self, alloc):
        Gtk.Window.do_map_event(self, alloc)  # type: ignore

        return self.set_pass_through(self._pass_through)


class Svg(FabricSvg):
    """
    Adds dynamic `color` support sourced from `Gtk.StyleContext`.
    """

    def do_draw(self, cr: cairo.Context):
        if not self._handle:
            return

        context = self.get_style_context()
        state = context.get_state()
        color = context.get_color(state)

        bridge_css = f"""
            * {{ 
                color: rgba({int(color.red * 255)}, {int(color.green * 255)}, {int(color.blue * 255)}, {color.alpha})
            }}
        """

        if self._style_compiled:
            final_style = bridge_css + self._style_compiled
        else:
            final_style = bridge_css

        if not self._handle.set_stylesheet(final_style.encode()):
            logger.error(
                "[Svg] Failed to apply styles, probably invalid style property"
            )

        alloc = self.get_allocation()
        width: int = alloc.width  # type: ignore
        height: int = alloc.height  # type: ignore

        rect = Rsvg.Rectangle()
        rect.x = rect.y = 0
        rect.width = width  # type: ignore
        rect.height = height  # type: ignore

        cr.save()
        self._handle.render_document(cr, rect)
        cr.restore()
