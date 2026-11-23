import cairo

from widgets.graphs import rounded_rect

from wm import glass_mode

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # type: ignore


def cut_slider_gap(
    scale: Gtk.Scale, radius: float = 4, gap: float | None = None
) -> None:
    if not glass_mode():
        return
    metrics: dict = {}  # css lookups per state cache
    scale.connect("style-updated", lambda *_: metrics.clear())
    scale.connect("draw", _begin)
    scale.connect_after("draw", _cut, radius, gap, metrics)
    # gtk only repaints the handle's box, not our gap, and the handle only
    # moves on allocate (the pill's offscreen can paint before that)
    scale.connect("size-allocate", lambda s, _a: s.queue_draw())


def _node(scale: Gtk.Scale, *names: str, state=Gtk.StateFlags.NORMAL):
    path = scale.get_path().copy()
    path.iter_set_state(-1, scale.get_state_flags())
    for name in names:
        path.append_type(GObject.TYPE_NONE)
        path.iter_set_object_name(-1, name)
    path.iter_set_state(-1, state)
    context = Gtk.StyleContext()
    context.set_path(path)
    context.set_parent(scale.get_style_context())
    return context


def _begin(_scale, cr) -> bool:
    cr.push_group()
    return False


def _measure(scale: Gtk.Scale, vertical: bool, held: Gtk.StateFlags):
    slider = _node(scale, "contents", "trough", "slider", state=held)
    trough = _node(scale, "contents", "trough")
    m = slider.get_margin(held)
    # trough stretches to fit the handle
    size = "min-width" if vertical else "min-height"
    side = (m.left + m.right) if vertical else (m.top + m.bottom)
    thickness = max(
        trough.get_property(size, 0), slider.get_property(size, held) + side
    )
    margins = (m.top, m.bottom) if vertical else (m.left, m.right)
    return *margins, thickness


def _cut(scale: Gtk.Scale, cr, radius: float, gap: float | None, metrics: dict) -> bool:
    vertical = scale.get_orientation() == Gtk.Orientation.VERTICAL
    held = (
        Gtk.StateFlags.ACTIVE
        if Gtk.grab_get_current() == scale
        else Gtk.StateFlags.NORMAL
    )
    key = (scale.get_state_flags(), held)
    if key not in metrics:
        metrics[key] = _measure(scale, vertical, held)
    lo_margin, hi_margin, thickness = metrics[key]

    start, end = scale.get_slider_range()
    lo, hi = start + lo_margin, end - hi_margin  # the drawn handle
    fill_end = (start + end) / 2  # highlight ends mid-handle
    rect = scale.get_range_rect()
    across = rect.width if vertical else rect.height
    centre = (rect.x if vertical else rect.y) + across / 2
    band = (centre - thickness / 2, thickness)

    if gap is None:
        gap = fill_end - hi if scale.get_inverted() else lo - fill_end
    # corners shrink near the edges so short stubs go flat
    first, last = (
        (rect.y, rect.y + rect.height) if vertical else (rect.x, rect.x + rect.width)
    )
    before, after = lo - gap, hi + gap
    r_before = max(0, min(radius, (before - first) / 2))
    r_after = max(0, min(radius, (last - after) / 2))
    ends = (
        (before - 2 * r_before, before, r_before),
        (after, after + 2 * r_after, r_after),
    )
    cut_from, cut_to = before - r_before, after + r_after

    def box(a, b, c0, c1):
        return (c0, a, c1, b - a) if vertical else (a, c0, b - a, c1)

    cr.save()
    cr.rectangle(*box(cut_from, cut_to, rect.x if vertical else rect.y, across))
    cr.clip_preserve()
    # keep the handle and the rounded track ends
    cr.rectangle(*box(lo, hi, rect.x if vertical else rect.y, across))
    for a, b, r in ends:
        if r > 0:
            rounded_rect(cr, *box(a, b, *band), r)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.fill()
    cr.restore()
    cr.pop_group_to_source()
    cr.paint()
    return False
