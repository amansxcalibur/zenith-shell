import math
from collections.abc import Callable
from dataclasses import dataclass, replace

import cairo

from fabric.widgets.box import Box

from services.animator import Animator

from .placement import DOCK_THICKNESS, DockPlacement

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

NOTCH_DURATION = 0.25  # seconds
NOTCH_CURVE = (0.5, 0.25, 0, 1)
NOTCH_FLARE = 20  # px, outward curve where a notch meets the inner edge
NOTCH_RADIUS = 20  # px, rounding of a notch's inner corners


@dataclass
class Notch:
    start: float = 0
    size: float = 0
    depth: float = 0
    flare: float = 0
    radius: float = NOTCH_RADIUS

    @property
    def end(self) -> float:
        return self.start + self.size

    @property
    def is_open(self) -> bool:
        return self.size > 0 and self.depth > 0


def trace_silhouette(
    cr: cairo.Context, length: float, thickness: float, notches: list[Notch]
) -> None:
    """Trace the dock's outline. Notches must be ordered and not overlap."""
    notches = [n for n in notches if n.is_open]

    cr.move_to(0, 0)
    for i, notch in enumerate(notches):
        # flares can't cross the screen edge and split the gap between notches
        before = notch.start if i == 0 else (notch.start - notches[i - 1].end) / 2
        after = (
            length - notch.end
            if i == len(notches) - 1
            else (notches[i + 1].start - notch.end) / 2
        )
        flare_before = max(0, min(notch.flare, before, notch.depth))
        flare_after = max(0, min(notch.flare, after, notch.depth))
        radius = min(notch.radius, notch.depth, notch.size / 2)

        # flares sit outside the notch and corners inside it, so the two may
        # share a stretch of depth (a shallow notch) without crossing
        cr.line_to(notch.start - flare_before, 0)
        if flare_before > 0:
            cr.arc(
                notch.start - flare_before,
                flare_before,
                flare_before,
                -math.pi / 2,
                0,
            )
        cr.line_to(notch.start, notch.depth - radius)
        cr.arc_negative(
            notch.start + radius,
            notch.depth - radius,
            radius,
            math.pi,
            math.pi / 2,
        )
        cr.line_to(notch.end - radius, notch.depth)
        cr.arc_negative(
            notch.end - radius,
            notch.depth - radius,
            radius,
            math.pi / 2,
            0,
        )
        cr.line_to(notch.end, flare_after)
        if flare_after > 0:
            cr.arc(
                notch.end + flare_after,
                flare_after,
                flare_after,
                math.pi,
                3 * math.pi / 2,
            )

    cr.line_to(length, 0)
    cr.line_to(length, thickness)
    cr.line_to(0, thickness)
    cr.close_path()


class AnimatedNotch:
    def __init__(
        self,
        tick_widget: Gtk.Widget,
        on_change: Callable[[], None],
        radius: float = NOTCH_RADIUS,
    ):
        self.current = Notch(radius=radius)
        self._from = replace(self.current)
        self._to = replace(self.current)
        self._on_change = on_change
        self._animator = Animator(
            bezier_curve=NOTCH_CURVE,
            duration=NOTCH_DURATION,
            min_value=0,
            max_value=1,
            tick_widget=tick_widget,
            notify_value=lambda p, *_: self._on_tick(p.value),
        )

    @property
    def animating(self) -> bool:
        return self._animator.playing

    @property
    def target(self) -> Notch:
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
            name="dock-surface", orientation=placement.orientation, **kwargs
        )
        self.placement = placement
        self.add_style_class(placement.style_class)
        self._notches: list[AnimatedNotch] = []

    def add_notch(self, radius: float = NOTCH_RADIUS) -> AnimatedNotch:
        """Add a notch. Call in the order the notches appear along the dock."""
        notch = AnimatedNotch(self, self.queue_draw, radius)
        self._notches.append(notch)
        return notch

    @property
    def thickness(self) -> int:
        size = self.placement.thickness(
            self.get_allocated_width(), self.get_allocated_height()
        )
        return size if size > 1 else DOCK_THICKNESS

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

        cr.save()
        cr.save()
        self.placement.transform(cr, width, height)
        trace_silhouette(
            cr,
            self.placement.length(width, height),
            self.placement.thickness(width, height),
            [notch.current for notch in self._notches],
        )
        cr.restore()  # the path keeps its device coordinates
        cr.clip()
        Gtk.render_background(self.get_style_context(), cr, 0, 0, width, height)
        cr.restore()

        # not Box.do_draw: that would paint the background over the whole box
        for child in self.get_children():
            self.propagate_draw(child, cr)
        return False
