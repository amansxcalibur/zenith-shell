import math
import time
import cairo
from collections import deque

from config.info import ROOT_DIR
from utils.colors import hex_to_rgb01, get_css_variable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

class AnimatedBarGraph(Gtk.DrawingArea):
    DEFAULT_HISTORY = 30

    def __init__(
        self,
        color: str | tuple = (0.1, 0.6, 0.9),
        bar_width: int = 4,
        spacing: int = 8,
        history_seconds: int = DEFAULT_HISTORY,
    ):
        super().__init__()
        self.set_size_request(350, 250)

        self.color = color
        self.bar_width = bar_width
        self.spacing = spacing
        self.growth_dur = 0.5  # seconds for a bar to reach full height

        # history_seconds sets how many data points we keep and how fast
        # the bars scroll (pixels_per_second adapts so history always fits)
        self._history_seconds = history_seconds
        self._sync_scroll_speed()

        self.data: deque[dict] = deque()

        self.connect("draw", self._on_draw)
        self.add_tick_callback(self._tick)
        self.show_all()

    def add_value(self, value: float) -> None:
        self.data.append({"val": value, "time": time.time()})
        self._trim_data()
        self.queue_draw()

    def set_history(self, seconds: int) -> None:
        self._history_seconds = max(5, seconds)
        self._sync_scroll_speed()
        self._trim_data()
        self.queue_draw()

    def _sync_scroll_speed(self) -> None:
        ref_width = 350
        # pps - total horizontal pixels allocated to 1 second of history
        pps = ref_width / max(1, self._history_seconds)
        self.pixels_per_second = pps

        spacing_ratio = 30 / self._history_seconds
        self.spacing = max(2.0, min(8.0, 8.0 * spacing_ratio))

        calculated_width = pps - self.spacing

        self.bar_width = max(2.0, min(50.0, calculated_width))

    def _trim_data(self) -> None:
        cutoff = time.time() - self._history_seconds - 1  # keep one extra
        while self.data and self.data[0]["time"] < cutoff:
            self.data.popleft()

    def _tick(self, widget, frame_clock) -> bool:
        self.queue_draw()
        return True

    def _on_draw(self, widget, cr) -> bool:
        alloc = self.get_allocation()
        width = alloc.width
        height = alloc.height
        now = time.time()

        pps = width / max(1, self._history_seconds)

        for item in reversed(self.data):
            age = now - item["time"]
            x_pos = width - (age * pps) - self.spacing

            if x_pos < -self.bar_width:
                break  # data is sorted; nothing older will be visible

            growth_progress = min(1.0, age / self.growth_dur)
            eased = 1 - pow(1 - growth_progress, 3)  # ease-out cubic
            target_h = (item["val"] / 100.0) * height
            current_h = target_h * eased

            self._draw_rounded_bar(
                cr, x_pos, height - current_h, self.bar_width, current_h
            )

        return False

    def _draw_rounded_bar(self, cr, x: float, y: float, w: float, h: float) -> None:
        if h < 2:
            return
        radius = min(6, w // 2)
        cr.new_sub_path()
        cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
        cr.arc(x + w - radius, y + radius, radius, 3 * math.pi / 2, 2 * math.pi)
        cr.line_to(x + w, y + h)
        cr.line_to(x, y + h)
        cr.close_path()

        hr_r, hr_g, hr_b = hex_to_rgb01(
            get_css_variable(f"{ROOT_DIR}/styles/colors.css", "--surface-bright")
        )
        cr.set_source_rgba(hr_r, hr_g, hr_b, 1.0)

        cr.fill()


class CircularGraph(Gtk.DrawingArea):
    EPSILON = 0.001
    LERP_SPEED = 0.1
    INNER_RADIUS = 70
    MAX_EXTRA_RAD = 100

    def __init__(self, bar_count: int):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.bar_count = bar_count
        self.current_usage = [0.0] * self.bar_count
        self.target_usage = [0.0] * self.bar_count
        self.is_animating = False

        self.connect("draw", self._on_draw)
        
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
        cr.set_line_width(4)

        for i, usage in enumerate(self.current_usage):
            angle = (i / self.bar_count) * 2 * math.pi

            r_inner = self.INNER_RADIUS
            r_outer = r_inner + usage / 100.0 * self.MAX_EXTRA_RAD

            hr_r, hr_g, hr_b = hex_to_rgb01(
                get_css_variable(f"{ROOT_DIR}/styles/colors.css", "--surface-bright")
            )
            cr.set_source_rgba(hr_r, hr_g, hr_b, 1.0)

            cr.move_to(math.cos(angle) * r_inner, math.sin(angle) * r_inner)
            cr.line_to(math.cos(angle) * r_outer, math.sin(angle) * r_outer)
            cr.stroke()

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
