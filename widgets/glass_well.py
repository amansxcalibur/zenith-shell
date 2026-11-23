import cairo
import functools
from collections.abc import Callable, Iterable

from widgets.graphs import rounded_rect

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore


def cut_page_out_of_well(well: Gtk.Widget, page: Gtk.Widget) -> None:
    cut_out_of_well(well, lambda: (page,))


def cut_out_of_well(
    well: Gtk.Widget,
    holes: Callable[[], Iterable[Gtk.Widget]],
    color: str | None = "glass-well",
    clip: Gtk.Widget | None = None,
    css_holes: bool = False,
) -> None:
    well.connect("draw", _draw_well, holes, color, clip, css_holes)


@functools.cache
def fit_wm_corners() -> None:
    from wm import wm_corner_radius

    if (r := wm_corner_radius()) is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(
        (
            f"#settings, .file-chooser-dialog {{ border-radius: {r}px; }}"
            f"#settings-header {{ border-radius: {r}px {r}px 0 0; }}"
        ).encode()
    )
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
    )


def glass_file_chooser(dialog: Gtk.FileChooserDialog) -> None:
    fit_wm_corners()
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


def _css_hole(cr, hole: Gtk.Widget, box) -> None:
    # the hole's own css shape, so per-corner radii (:last-child etc) carry over
    context = hole.get_style_context()
    context.save()
    context.add_class("well-hole")
    Gtk.render_background(context, cr, *box[:4])
    context.restore()


def _draw_well(well, cr, holes, color_name, clip, css_holes) -> bool:
    context = well.get_style_context()
    if color_name is None:
        color = context.get_property("outline-color", well.get_state_flags())
    else:
        found, color = context.lookup_color(color_name)
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
            if css_holes:
                _css_hole(cr, hole, box)
            else:
                rounded_rect(cr, *box)
    cr.fill()
    cr.pop_group_to_source()
    cr.paint()
    return False
