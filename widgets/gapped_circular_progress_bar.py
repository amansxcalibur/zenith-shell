import math
import cairo

from fabric.utils.helpers import clamp
from fabric.widgets.circularprogressbar import CircularProgressBar

from gi.repository import Gdk  # type: ignore


class GappedCircularProgressBar(CircularProgressBar):
    def __init__(self, gap: float = 3.0, **kwargs):
        kwargs.setdefault("line_style", "round")
        super().__init__(**kwargs)
        self._gap = gap

    @property
    def gap(self) -> float:
        return self._gap

    @gap.setter
    def gap(self, value: float):
        self._gap = max(0.0, value)
        self.queue_draw()

    def _draw_segment(self, cr, cx, cy, radius, line_width, a0, a1):
        """Stroke the angular region [a0, a1] including its line caps. If the region
        is too small to fit the caps, shrink it down to a dot."""
        available = a1 - a0
        if available <= 0:
            return
        cap_angle = line_width / radius if self._line_style != cairo.LineCap.BUTT else 0
        if available >= cap_angle:
            cr.set_line_width(line_width)
            # tiny delta so butt/square caps still render a zero-length arc
            start = a0 + cap_angle / 2
            end = max(a1 - cap_angle / 2, start + 1e-4)
            cr.arc(cx, cy, radius, start, end)
        else:
            mid = (a0 + a1) / 2
            cr.set_line_width(min(line_width, 2 * radius * math.sin(available / 2)))
            cr.arc(cx, cy, radius, mid, mid + 1e-4)
        cr.stroke()

    def do_draw(self, cr: cairo.Context):
        state = self.get_state_flags()
        ctx = self.get_style_context()

        border = ctx.get_border(state)
        trough_color = ctx.get_color(state)
        progress_color = ctx.get_border_color(state)
        background_color = ctx.get_background_color(state)

        line_width = max(
            self._line_width,
            border.top,
            border.bottom,
            border.left,
            border.right,
        )

        cx = self.get_allocated_width() / 2
        cy = self.get_allocated_height() / 2
        outer_radius = self.do_calculate_radius()
        radius = outer_radius - line_width / 2
        if radius <= 0:
            if child := self.get_child():
                self.propagate_draw(child, cr)
            return

        cr.save()
        cr.set_line_cap(self._line_style)

        # background fill
        Gdk.cairo_set_source_rgba(cr, background_color)
        cr.arc(cx, cy, outer_radius, 0, 2 * math.pi)
        cr.fill()

        start = math.radians(self._start_angle)
        end = math.radians(self._end_angle)
        sweep = end - start
        if sweep < 0:
            start, end, sweep = end, start, -sweep
        closed = sweep >= 2 * math.pi - 1e-6

        value_range = self._max_value - self._min_value
        norm = (
            clamp((self._value - self._min_value) / value_range, 0.0, 1.0)
            if value_range
            else 0.0
        )

        # fade the gap out as the value approaches either end, so 0 is a full
        # trough ring and 1 a full progress ring without a visual jump
        gap_angle = self._gap / radius
        cap_angle = line_width / radius
        edge = (gap_angle + cap_angle) / sweep if sweep else 1.0
        if edge > 0:
            gap_angle *= clamp(min(norm, 1.0 - norm) / edge, 0.0, 1.0)

        progress_angle = start + norm * sweep

        head = progress_angle - gap_angle / 2  # leading edge of the progress
        dot_half = clamp(head - start, 0.0, cap_angle / 2)  # start cap half-size
        trough_end = end - (dot_half + gap_angle if closed else 0.0)
        if closed:
            # near full, don't let the head run into the start cap
            head = min(head, trough_end)

        if closed and gap_angle == 0 and norm in (0.0, 1.0):
            Gdk.cairo_set_source_rgba(cr, progress_color if norm else trough_color)
            cr.set_line_width(line_width)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()
        else:
            Gdk.cairo_set_source_rgba(cr, trough_color)
            self._draw_segment(
                cr,
                cx,
                cy,
                radius,
                line_width,
                progress_angle + gap_angle / 2,
                trough_end,
            )
            Gdk.cairo_set_source_rgba(cr, progress_color)
            if dot_half >= cap_angle / 2:
                cr.set_line_width(line_width)
                cr.arc(cx, cy, radius, start, max(head - cap_angle / 2, start + 1e-4))
                cr.stroke()
            elif dot_half > 0:
                cr.set_line_width(2 * radius * math.sin(dot_half))
                cr.arc(cx, cy, radius, start, start + 1e-4)
                cr.stroke()

        if child := self.get_child():
            self.propagate_draw(child, cr)

        cr.restore()
