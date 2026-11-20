from collections.abc import Callable, Iterable

import cairo

from widgets.graphs import rounded_rect

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore


def cut_page_out_of_well(well: Gtk.Widget, page: Gtk.Widget) -> None:
    cut_out_of_well(well, lambda: (page,))


def cut_out_of_well(
    well: Gtk.Widget,
    holes: Callable[[], Iterable[Gtk.Widget]],
    color: str = "glass-well",
    clip: Gtk.Widget | None = None,
) -> None:
    well.connect("draw", _draw_well, holes, color, clip)


def glass_file_chooser(dialog: Gtk.FileChooserDialog) -> None:
    dialog.get_style_context().add_class("glass")
    chooser = dialog.get_content_area().get_children()[0]
    well = chooser.get_children()[0]
    paned = well.get_children()[0]
    cut_page_out_of_well(well, paned.get_child2())


def _box(widget: Gtk.Widget, well: Gtk.Widget):
    coords = widget.translate_coordinates(well, 0, 0)
    if coords is None:
        return None
    context = widget.get_style_context()
    state = widget.get_state_flags()
    m = context.get_margin(state)  # inside the allocation in GTK3
    return (
        coords[0] + m.left,
        coords[1] + m.top,
        widget.get_allocated_width() - m.left - m.right,
        widget.get_allocated_height() - m.top - m.bottom,
        context.get_property("border-radius", state),
    )


def _draw_well(well, cr, holes, color_name, clip) -> bool:
    found, color = well.get_style_context().lookup_color(color_name)
    if not found:
        return False
    cr.push_group()
    rounded_rect(cr, *_box(well, well))
    Gdk.cairo_set_source_rgba(cr, color)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_source_rgba(0, 0, 0, 1)  # the holes go all the way through
    if clip is not None and (box := _box(clip, well)):
        rounded_rect(cr, *box)
        cr.clip()
    for hole in holes():
        if hole.get_mapped() and (box := _box(hole, well)):
            rounded_rect(cr, *box)
    cr.fill()
    cr.pop_group_to_source()
    cr.paint()
    return False
