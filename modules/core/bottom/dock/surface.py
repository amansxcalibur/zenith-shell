import math
import cairo
from collections.abc import Callable
from dataclasses import dataclass, replace

from fabric.widgets.box import Box

from services.animator import Animator

from config.config import config

from .placement import (
    DOCK_EDGE_BAND,
    DOCK_PADDING,
    DOCK_THICKNESS,
    MODULE_RADIUS,
    DockPlacement,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore

BORDER_WIDTH = 1  # px, colored by the stylesheet's border-color
HOLE_DURATION = 0.25  # seconds
HOLE_CURVE = (0.5, 0.25, 0, 1)
# concentric with the modules' corners across the padding around them, so the
# gap holds around the hovered module (radius) and its neighbours (flare)
HOLE_FLARE = MODULE_RADIUS + DOCK_PADDING  # px, curve where a hole meets the edge
HOLE_RADIUS = MODULE_RADIUS + DOCK_PADDING  # px, rounding of a hole's inner corners


@dataclass
class Hole:
    start: float = 0
    size: float = 0
    depth: float = 0
    flare: float = 0
    radius: float = HOLE_RADIUS

    @property
    def end(self) -> float:
        return self.start + self.size

    @property
    def is_open(self) -> bool:
        return self.size > 0 and self.depth > 0


def trace_inner_edge(cr: cairo.Context, length: float, holes: list[Hole]) -> None:
    """Trace the edge facing away from the screen. Holes must be ordered and not overlap."""
    holes = [n for n in holes if n.is_open]

    cr.move_to(0, 0)
    for i, hole in enumerate(holes):
        # flares can't cross the screen edge and split the gap between holes
        before = hole.start if i == 0 else (hole.start - holes[i - 1].end) / 2
        after = (
            length - hole.end
            if i == len(holes) - 1
            else (holes[i + 1].start - hole.end) / 2
        )
        flare_before = max(0, min(hole.flare, before, hole.depth))
        flare_after = max(0, min(hole.flare, after, hole.depth))
        radius = min(hole.radius, hole.depth, hole.size / 2)

        # flares sit outside the hole and corners inside it, so the two may
        # share a stretch of depth (a shallow hole) without crossing
        cr.line_to(hole.start - flare_before, 0)
        if flare_before > 0:
            cr.arc(
                hole.start - flare_before,
                flare_before,
                flare_before,
                -math.pi / 2,
                0,
            )
        cr.line_to(hole.start, hole.depth - radius)
        cr.arc_negative(
            hole.start + radius,
            hole.depth - radius,
            radius,
            math.pi,
            math.pi / 2,
        )
        cr.line_to(hole.end - radius, hole.depth)
        cr.arc_negative(
            hole.end - radius,
            hole.depth - radius,
            radius,
            math.pi / 2,
            0,
        )
        cr.line_to(hole.end, flare_after)
        if flare_after > 0:
            cr.arc(
                hole.end + flare_after,
                flare_after,
                flare_after,
                math.pi,
                3 * math.pi / 2,
            )

    cr.line_to(length, 0)


def trace_silhouette(
    cr: cairo.Context, length: float, thickness: float, holes: list[Hole]
) -> None:
    """Trace the dock's outline. Holes must be ordered and not overlap."""
    trace_inner_edge(cr, length, holes)
    cr.line_to(length, thickness)
    cr.line_to(0, thickness)
    cr.close_path()


class AnimatedHole:
    def __init__(
        self,
        tick_widget: Gtk.Widget,
        on_change: Callable[[], None],
        radius: float = HOLE_RADIUS,
    ):
        self.current = Hole(radius=radius)
        self._from = replace(self.current)
        self._to = replace(self.current)
        self._on_change = on_change
        self._animator = Animator(
            bezier_curve=HOLE_CURVE,
            duration=HOLE_DURATION,
            min_value=0,
            max_value=1,
            tick_widget=tick_widget,
            notify_value=lambda p, *_: self._on_tick(p.value),
        )

    @property
    def animating(self) -> bool:
        return self._animator.playing

    @property
    def target(self) -> Hole:
        return self._to

    def animate_to(self, **values: float) -> None:
        if all(getattr(self._to, key) == value for key, value in values.items()):
            return

        self._from = replace(self.current)
        self._to = replace(self._to, **values)
        self._animator.pause()
        self._animator.value = 0
        self._animator.play()

    def jump_to(self, **values: float) -> None:
        """Set values now, leaving any other value's animation running."""
        for key, value in values.items():
            setattr(self.current, key, value)
            setattr(self._from, key, value)
            setattr(self._to, key, value)
        self._on_change()

    def _on_tick(self, progress: float) -> None:
        for key in ("start", "size", "depth", "flare"):
            start, end = getattr(self._from, key), getattr(self._to, key)
            setattr(self.current, key, start + (end - start) * progress)
        self._on_change()


class DockSurface(Box):
    def __init__(self, placement: DockPlacement, **kwargs):
        super().__init__(
            name="dock-surface",
            orientation=placement.orientation,
            style=placement.thickness_style,
            **kwargs,
        )
        self._show_border: bool = config.get("bar.BORDER")
        self.placement = placement
        self.add_style_class(placement.style_class)
        self._holes: list[AnimatedHole] = []

    def add_hole(self, radius: float = HOLE_RADIUS) -> AnimatedHole:
        hole = AnimatedHole(self, self.queue_draw, radius)
        self._holes.append(hole)
        return hole

    @property
    def thickness(self) -> int:
        size = self.placement.thickness(
            self.get_allocated_width(), self.get_allocated_height()
        )
        return size if size > 1 else DOCK_THICKNESS

    @property
    def hole_depth(self) -> int:
        # short of the screen edge, so the border stays visible along the floor
        return self.thickness - DOCK_EDGE_BAND

    def rect_along(self, widget: Gtk.Widget) -> tuple[int, int] | None:
        """(start, size) of a descendant on the dock's main axis."""
        coords = widget.translate_coordinates(self, 0, 0)
        if coords is None:
            return None
        return self.placement.along(
            coords[0],
            coords[1],
            widget.get_allocated_width(),
            widget.get_allocated_height(),
        )

    def do_draw(self, cr: cairo.Context) -> bool:
        width, height = self.get_allocated_width(), self.get_allocated_height()
        length = self.placement.length(width, height)
        holes = [hole.current for hole in self._holes]
        context = self.get_style_context()

        cr.save()
        cr.save()
        self.placement.transform(cr, width, height)
        trace_silhouette(cr, length, self.placement.thickness(width, height), holes)
        cr.restore()  # the path keeps its device coordinates
        cr.clip()
        Gtk.render_background(context, cr, 0, 0, width, height)

        if self._show_border:
            cr.save()
            self.placement.transform(cr, width, height)
            trace_inner_edge(cr, length, holes)
            cr.restore()
            # still clipped, so only the half inside the dock shows
            cr.set_line_width(BORDER_WIDTH * 2)
            Gdk.cairo_set_source_rgba(
                cr, context.get_property("border-top-color", context.get_state())
            )
            cr.stroke()
        cr.restore()

        # not Box.do_draw: that would paint the background over the whole box
        for child in self.get_children():
            self.propagate_draw(child, cr)
        return False
