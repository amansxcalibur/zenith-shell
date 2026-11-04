import math
import time
import cairo
from collections import deque

from expressive_shapes.geometry.rounded_polygon import RoundedPolygon
from expressive_shapes.morph.bezier_morph import Morph

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, GLib  # type: ignore


def theme_color(widget, name: str) -> Gdk.RGBA:
    context = widget.get_style_context()
    found, color = context.lookup_color(name)
    return color if found else context.get_color(widget.get_state_flags())


def rounded_rect(cr, x: float, y: float, w: float, h: float, radius: float) -> None:
    radius = min(radius, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


class TickingArea(Gtk.DrawingArea):
    """Drawing area that redraws every frame, but only while on screen."""

    def __init__(self):
        super().__init__()
        self._tick_id = None
        self._animated = True
        self.connect("map", lambda *_: self._sync_ticking(True))
        self.connect("unmap", lambda *_: self._sync_ticking(False))
        self.connect("draw", self._on_draw)

    def set_animated(self, animated: bool) -> None:
        """False (e.g. power saving) settles instantly and only draws on changes."""
        self._animated = animated
        self._sync_ticking(self.get_mapped())
        self.queue_draw()

    def _sync_ticking(self, mapped: bool) -> None:
        if mapped and self._animated and self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._tick)
        elif not (mapped and self._animated) and self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None

    def _tick(self, widget, frame_clock) -> bool:
        self.queue_draw()
        return True

    def _on_draw(self, widget, cr) -> bool:
        raise NotImplementedError


class AnimatedBarGraph(TickingArea):
    """Scrolling 0-100 bar graph. Bars take the CSS `color`; the newest is `--primary`."""

    DEFAULT_HISTORY = 30
    MAX_HISTORY = 120
    GROWTH_DURATION = 0.5  # seconds for a bar to reach full height

    def __init__(
        self,
        history_seconds: int = DEFAULT_HISTORY,
        top_inset: int = 0,
        size: tuple[int, int] = (350, 250),
    ):
        """`top_inset` is headroom (px) that full-height bars stop short of."""
        super().__init__()
        self.set_size_request(*size)
        self.get_style_context().add_class("metrics-graph")

        self.top_inset = top_inset
        self._history_seconds = history_seconds
        self.data: deque[tuple] = deque()  # (timestamp, value, ...)

        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._on_query_tooltip)
        self.show_all()

    def add_value(self, *values: float) -> None:
        self.data.append((time.monotonic(), *values))
        # always keep the full range so widening the window reveals past data
        cutoff = time.monotonic() - self.MAX_HISTORY - 1  # keep one extra
        while self.data and self.data[0][0] < cutoff:
            self.data.popleft()
        self.queue_draw()

    def set_history(self, seconds: int) -> None:
        self._history_seconds = max(5, seconds)
        self.queue_draw()

    def _bar_geometry(self, width: int) -> tuple[float, float, float]:
        """(pixels per second, spacing right of a bar, bar width); fits any width."""
        pps = width / self._history_seconds
        bar_width = min(24.0, max(1.5, pps * 0.32))
        return pps, max(1.0, pps - bar_width), bar_width

    def _visible_bars(self, width: int):
        """Yield (item, x, growth) for on-screen bars, newest first."""
        now = time.monotonic()
        pps, spacing, bar_width = self._bar_geometry(width)
        for item in reversed(self.data):
            age = now - item[0]
            x = width - age * pps - spacing
            if x < -bar_width:
                break  # data is sorted; nothing older will be visible
            progress = min(1.0, age / self.GROWTH_DURATION)
            yield item, x, 1 - (1 - progress) ** 3  # ease-out cubic

    def _on_draw(self, widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        _, _, bar_width = self._bar_geometry(width)
        usable = height - self.top_inset

        Gdk.cairo_set_source_rgba(cr, theme_color(self, "primary"))
        for index, (item, x, growth) in enumerate(self._visible_bars(width)):
            if index == 1:  # only the newest bar is highlighted
                Gdk.cairo_set_source_rgba(
                    cr, self.get_style_context().get_color(self.get_state_flags())
                )
            bar_height = item[1] / 100.0 * usable * growth
            self._draw_bar(cr, x, height - bar_height, bar_width, bar_height)
        return False

    @staticmethod
    def _draw_bar(cr, x: float, y: float, w: float, h: float) -> None:
        """Rounded at the top, square at the baseline."""
        if h < 2:
            return
        radius = min(4, w / 2, h)
        cr.new_sub_path()
        cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
        cr.arc(x + w - radius, y + radius, radius, 3 * math.pi / 2, 2 * math.pi)
        cr.line_to(x + w, y + h)
        cr.line_to(x, y + h)
        cr.close_path()
        cr.fill()

    def _on_query_tooltip(self, widget, x, y, keyboard, tooltip) -> bool:
        if not self.data or y < self.top_inset:
            return False
        width = self.get_allocated_width()
        pps, spacing, _ = self._bar_geometry(width)
        age = (width - spacing - x) / pps
        now = time.monotonic()
        item = min(self.data, key=lambda i: abs(now - i[0] - age))
        tooltip.set_text(f"{self._format_item(item)} · {now - item[0]:.0f}s ago")
        return True

    def _format_item(self, item: tuple) -> str:
        return f"{item[1]:.0f}%"


class MirroredBarGraph(AnimatedBarGraph):
    """Two series on one scale: `--primary` above a baseline, `--outline` below it.

    The baseline moves with the balance between the series, so a lopsided load (say,
    downloads with little upload) still fills the graph. Both sides always share
    the same pixels-per-unit, so their bars stay directly comparable.
    """

    MIN_PEAK = 64 * 1024  # keeps idle noise from filling the graph
    SMOOTHING = 0.08
    MIN_SPLIT = 0.2  # neither side gets less than this share of the height
    BASELINE_GAP = 2

    def __init__(self, format_value=str, **kwargs):
        super().__init__(**kwargs)
        self._format_value = format_value
        self.peak = self.MIN_PEAK  # largest visible value, in data units
        self._split = 0.5  # share of the height above the baseline
        self._px_per_unit = None

    def _on_draw(self, widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        _, _, bar_width = self._bar_geometry(width)
        bars = list(self._visible_bars(width))

        top_peak = max(max((item[1] for item, _, _ in bars), default=0), self.MIN_PEAK)
        bottom_peak = max(
            max((item[2] for item, _, _ in bars), default=0), self.MIN_PEAK
        )
        self.peak = max(top_peak, bottom_peak)

        usable = height - self.top_inset - 2 * self.BASELINE_GAP
        split = top_peak / (top_peak + bottom_peak)
        split = max(self.MIN_SPLIT, min(1 - self.MIN_SPLIT, split))
        px_per_unit = min(split * usable / top_peak, (1 - split) * usable / bottom_peak)

        smoothing = self.SMOOTHING if self._animated else 1
        if self._px_per_unit is None:
            self._px_per_unit = px_per_unit
        self._px_per_unit += (px_per_unit - self._px_per_unit) * smoothing
        self._split += (split - self._split) * smoothing

        top_space = self._split * usable
        bottom_space = usable - top_space
        baseline = self.top_inset + self.BASELINE_GAP + top_space

        Gdk.cairo_set_source_rgba(cr, theme_color(self, "surface-bright"))
        cr.rectangle(0, baseline - 0.5, width, 1)
        cr.fill()

        Gdk.cairo_set_source_rgba(cr, theme_color(self, "primary"))
        for item, x, growth in bars:
            h = min(top_space, item[1] * self._px_per_unit) * growth
            self._draw_bar(cr, x, baseline - self.BASELINE_GAP - h, bar_width, h)

        # below the baseline: same bar, mirrored
        Gdk.cairo_set_source_rgba(cr, theme_color(self, "outline"))
        cr.save()
        cr.translate(0, 2 * baseline)
        cr.scale(1, -1)
        for item, x, growth in bars:
            h = min(bottom_space, item[2] * self._px_per_unit) * growth
            self._draw_bar(cr, x, baseline - self.BASELINE_GAP - h, bar_width, h)
        cr.restore()
        return False

    def _format_item(self, item: tuple) -> str:
        return f"↓ {self._format_value(item[1])}  ↑ {self._format_value(item[2])}"


class CircularGraph(Gtk.DrawingArea):
    """Radial per-core graph. Bars take their color from the CSS `color` property."""

    EPSILON = 0.001
    LERP_SPEED = 0.1
    INNER_RADIUS = 56
    LINE_WIDTH = 4

    def __init__(self, bar_count: int):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.get_style_context().add_class("metrics-graph")

        self.bar_count = bar_count
        self.current_usage = [0.0] * self.bar_count
        self.target_usage = [0.0] * self.bar_count
        self.is_animating = False

        self.connect("draw", self._on_draw)
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._on_query_tooltip)

        self.show_all()

    def _update_targets(self, targets: list) -> bool:
        self.target_usage = targets

        # rather skip quick updates than get stuck in
        # the middle due to fast updates
        if not self.is_animating:
            self.is_animating = True
            GLib.timeout_add(33, self._animate)
        return True

    def _animate(self) -> bool:
        still_moving = False

        for i in range(self.bar_count):
            diff = self.target_usage[i] - self.current_usage[i]

            if abs(diff) > self.EPSILON:
                self.current_usage[i] += diff * self.LERP_SPEED
                still_moving = True
            else:
                self.current_usage[i] = self.target_usage[i]

        self.queue_draw()

        if not still_moving:
            self.is_animating = False
            return False

        return True

    def _on_draw(self, widget, cr) -> bool:
        cx = self.get_allocated_width() / 2
        cy = self.get_allocated_height() / 2

        cr.translate(cx, cy)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_width(self.LINE_WIDTH)
        Gdk.cairo_set_source_rgba(
            cr, self.get_style_context().get_color(self.get_state_flags())
        )

        # 100% reaches the edge of the widget (leaving room for the round cap)
        max_extent = max(0, min(cx, cy) - self.LINE_WIDTH / 2 - self.INNER_RADIUS)

        for i, usage in enumerate(self.current_usage):
            angle = (i / self.bar_count) * 2 * math.pi

            r_inner = self.INNER_RADIUS
            r_outer = r_inner + usage / 100.0 * max_extent

            cr.move_to(math.cos(angle) * r_inner, math.sin(angle) * r_inner)
            cr.line_to(math.cos(angle) * r_outer, math.sin(angle) * r_outer)
            cr.stroke()

        return False

    def _on_query_tooltip(self, widget, x, y, keyboard, tooltip) -> bool:
        dx = x - self.get_allocated_width() / 2
        dy = y - self.get_allocated_height() / 2
        if math.hypot(dx, dy) < self.INNER_RADIUS:
            return False
        angle = math.atan2(dy, dx) % (2 * math.pi)
        index = round(angle / (2 * math.pi) * self.bar_count) % self.bar_count
        tooltip.set_text(f"Thread {index}: {self.target_usage[index]:.0f}%")
        return True


class LoadShape(TickingArea):
    """Expressive backdrop: spins faster under load and morphs when `hot`.

    Fill is the CSS `color`, outline is the CSS `border-color`.
    """

    MIN_SPEED = 0.04  # radians per second at idle
    MAX_SPEED = 0.9  # ...and at 100% load
    MORPH_DURATION = 0.5

    def __init__(self, calm_shape, hot_shape):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_name("metrics-load-shape")

        self._mappings = Morph.match(
            self._polygon(calm_shape), self._polygon(hot_shape)
        )
        self._curves = Morph.as_cubics(self._mappings, 0.0)
        self._angle = 0.0
        self._load = 0.0
        self._hot = False
        self._progress = 0.0
        self._last_frame = None
        self.show_all()

    @staticmethod
    def _polygon(preset) -> RoundedPolygon:
        vertices, rounding = [], []
        for (x, y), corner in preset:
            vertices += [x, y]
            rounding.append(corner)
        return RoundedPolygon.create(vertices=vertices, per_vertex_rounding=rounding)

    def set_load(self, fraction: float, hot: bool) -> None:
        self._load = max(0.0, min(1.0, fraction))
        self._hot = hot
        if not self._animated or not self.get_mapped():
            self._set_progress(1.0 if hot else 0.0)
            self.queue_draw()

    def _set_progress(self, progress: float) -> None:
        if progress != self._progress:
            self._progress = progress
            eased = (1 - math.cos(math.pi * progress)) / 2
            self._curves = Morph.as_cubics(self._mappings, eased)

    def _tick(self, widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time() / 1_000_000
        dt = min(0.1, now - self._last_frame) if self._last_frame else 0.0
        self._last_frame = now

        speed = self.MIN_SPEED + self._load * (self.MAX_SPEED - self.MIN_SPEED)
        self._angle = (self._angle + speed * dt) % (2 * math.pi)

        step = dt / self.MORPH_DURATION
        target = 1.0 if self._hot else 0.0
        self._set_progress(
            min(target, self._progress + step)
            if target > self._progress
            else max(target, self._progress - step)
        )
        self.queue_draw()
        return True

    def _on_draw(self, widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        side = min(width, height)
        if not self._curves or not side:
            return False

        context = self.get_style_context()
        flags = self.get_state_flags()

        cr.save()
        cr.translate(width / 2, height / 2)
        cr.rotate(self._angle)
        cr.scale(side, side)
        cr.translate(-0.5, -0.5)
        cr.move_to(self._curves[0].p0.x, self._curves[0].p0.y)
        for c in self._curves:
            cr.curve_to(c.p1.x, c.p1.y, c.p2.x, c.p2.y, c.p3.x, c.p3.y)
        cr.close_path()
        cr.restore()

        Gdk.cairo_set_source_rgba(cr, context.get_color(flags))
        cr.fill_preserve()
        Gdk.cairo_set_source_rgba(cr, context.get_border_color(flags))
        cr.set_line_width(1.5)
        cr.stroke()
        return False


class WavyProgress(TickingArea):
    """Material 3 Expressive wavy progress: wave up to the value, flat track after."""

    AMPLITUDE = 2.0
    WAVELENGTH = 18.0
    SPEED = 0.6  # waves per second
    LINE_WIDTH = 3.0
    GAP = 6.0  # between the wave and the track

    def __init__(self, size: tuple[int, int] = (70, 16)):
        super().__init__()
        self.set_size_request(*size)
        self.set_valign(Gtk.Align.CENTER)
        self._fraction = 0.0
        self._phase = 0.0
        self._last_frame = None
        self.show_all()

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.queue_draw()

    def _tick(self, widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time() / 1_000_000
        if self._last_frame:
            self._phase += min(0.1, now - self._last_frame) * self.SPEED
        self._last_frame = now
        self.queue_draw()
        return True

    def _on_draw(self, widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        mid = height / 2
        pad = self.LINE_WIDTH / 2
        end = pad + self._fraction * (width - self.LINE_WIDTH)

        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_join(cairo.LineJoin.ROUND)
        cr.set_line_width(self.LINE_WIDTH)

        if end + self.GAP < width - pad:
            Gdk.cairo_set_source_rgba(cr, theme_color(self, "surface-bright"))
            cr.move_to(end + self.GAP if self._fraction else pad, mid)
            cr.line_to(width - pad, mid)
            cr.stroke()

        if self._fraction > 0:
            Gdk.cairo_set_source_rgba(cr, theme_color(self, "primary"))
            cr.move_to(pad, mid)
            x = pad
            while x < end:
                x = min(end, x + 1.5)
                taper = min(1.0, (x - pad) / 8, (end - x) / 8)  # flat at both tips
                wave = math.sin(2 * math.pi * (x / self.WAVELENGTH - self._phase))
                cr.line_to(x, mid + wave * self.AMPLITUDE * taper)
            cr.stroke()
        return False


class LinearProgress(WavyProgress):
    """Same bar without the wave: a straight line that only redraws on changes."""

    AMPLITUDE = 0.0

    def __init__(self, size: tuple[int, int] = (70, 16)):
        super().__init__(size)
        self.set_animated(False)

    def set_animated(self, animated: bool) -> None:
        super().set_animated(False)


class SegmentedBar(Gtk.DrawingArea):
    """Part-to-whole bar: `set_segments([(fraction, theme color, alpha), ...])`."""

    GAP = 2.0

    def __init__(self, height: int = 10):
        super().__init__()
        self.set_size_request(-1, height)
        self.set_hexpand(True)
        self._segments: list[tuple[float, str, float]] = []
        self.connect("draw", self._on_draw)
        self.show_all()

    def set_segments(self, segments: list[tuple[float, str, float]]) -> None:
        self._segments = segments
        self.queue_draw()

    def _on_draw(self, widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        x = 0.0
        for fraction, color_name, alpha in self._segments:
            w = fraction * width
            if w >= 2:
                color = theme_color(self, color_name)
                cr.set_source_rgba(color.red, color.green, color.blue, alpha)
                rounded_rect(cr, x, 0, max(1.0, w - self.GAP), height, 4)
                cr.fill()
            x += w
        return False


class FillBar(Gtk.DrawingArea):
    """Rounded backdrop filled to a fraction, for text rows that read as bars."""

    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self._fraction = 0.0
        self.connect("draw", self._on_draw)
        self.show_all()

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.queue_draw()

    def _on_draw(self, widget, cr) -> bool:
        height = self.get_allocated_height()
        w = self._fraction * self.get_allocated_width()
        if w >= 2:
            Gdk.cairo_set_source_rgba(cr, theme_color(self, "surface-bright"))
            rounded_rect(cr, 0, 0, w, height, height / 2)
            cr.fill()
        return False


class UsageGraph(Gtk.DrawingArea):
    def __init__(self, color_rgb, max_points=10, base_padding=10):
        super().__init__()
        self.color = color_rgb
        self.base_padding = base_padding
        self.history = deque([0.0] * max_points, maxlen=max_points)
        self.set_size_request(420, 200)
        self.connect("draw", self.on_draw)
        self.show()

    def add_value(self, value):
        self.history.append(value)
        self.queue_draw()

    def get_ribbon_points(self, mid_y, step, thickness_factor):
        top = []
        bottom = []
        for i, val in enumerate(self.history):
            x = i * step
            half_width = (self.base_padding + (val * 0.8)) * thickness_factor
            top.append((x, mid_y - half_width))
            bottom.append((x, mid_y + half_width))
        return top, bottom

    def draw_smooth_path(self, cr, points, reverse=False):
        pts = list(reversed(points)) if reverse else points
        if not pts:
            return

        cr.line_to(pts[0][0], pts[0][1])
        tension = 0.4  # lower tension for smoother, lazier curves

        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i + 1]
            cp1x = p1[0] + (p2[0] - p1[0]) * tension
            cp2x = p2[0] - (p2[0] - p1[0]) * tension
            cr.curve_to(cp1x, p1[1], cp2x, p2[1], p2[0], p2[1])

    def on_draw(self, widget, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        mid_y = h / 2
        step = w / (self.history.maxlen - 1)

        # (thickness_scale, alpha_multiplier)
        layers = [
            (1.4, 0.2),  # Outer faint glow
            # (1.1, 0.2),  # Middle soft layer
            (1.0, 0.4),  # Inner solid body
            (0.6, 1.0),  # Dense core
        ]

        for scale, alpha in layers:
            top, bottom = self.get_ribbon_points(mid_y, step, scale)

            cr.set_source_rgba(self.color[0], self.color[1], self.color[2], alpha)

            # draw the polygon
            cr.move_to(top[0][0], top[0][1])
            self.draw_smooth_path(cr, top)
            cr.line_to(bottom[-1][0], bottom[-1][1])
            self.draw_smooth_path(cr, bottom, reverse=True)
            cr.close_path()
            cr.fill()

        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.set_line_width(1.0)
        top_outer, bottom_outer = self.get_ribbon_points(mid_y, step, 1.4)

        cr.move_to(top_outer[0][0], top_outer[0][1])
        self.draw_smooth_path(cr, top_outer)
        cr.stroke()

        cr.move_to(bottom_outer[0][0], bottom_outer[0][1])
        self.draw_smooth_path(cr, bottom_outer)
        cr.stroke()
