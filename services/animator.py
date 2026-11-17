from enum import Enum
from typing import cast
from fabric import Service, Signal, Property
from gi.repository import GLib, Gtk  # type: ignore

class CubicBezierCurves(tuple, Enum):
    EXPRESSIVE = (0.42, 1.67, 0.21, 1.0)
    EMPHASIS = (0.27, 1.0, 0.18, 1.0)
    STANDARD = (0.2, 0.0, 0.0, 1.0)

class Animator(Service):
    @Signal
    def finished(self) -> None: ...

    @Property(tuple[float, float, float, float], "read-write")
    def bezier_curve(self) -> tuple[float, float, float, float]:
        return self._bezier_curve

    @bezier_curve.setter
    def bezier_curve(self, value: tuple[float, float, float, float]):
        self._bezier_curve = value

    @Property(float, "read-write")
    def value(self):
        return self._value

    @value.setter
    def value(self, value: float):
        self._value = value

    @Property(float, "read-write")
    def max_value(self):
        return self._max_value

    @max_value.setter
    def max_value(self, value: float):
        self._max_value = value

    @Property(float, "read-write")
    def min_value(self):
        return self._min_value

    @min_value.setter
    def min_value(self, value: float):
        self._min_value = value

    @Property(float, "read-write")
    def max_overshoot_value(self):
        return self._max_overshoot_value

    @max_overshoot_value.setter
    def max_overshoot_value(self, value: float):
        self._max_overshoot_value = value

    @Property(bool, "read-write", default_value=False)
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, value: bool):
        self._playing = value

    @Property(bool, "read-write", default_value=False)
    def repeat(self):
        return self._repeat

    @repeat.setter
    def repeat(self, value: bool):
        self._repeat = value

    def __init__(
        self,
        bezier_curve: tuple[float, float, float, float],
        duration: float,
        min_value: float = 0.0,
        max_value: float = 1.0,
        max_overshoot_value: float = -1.0,
        repeat: bool = False,
        tick_widget: Gtk.Widget | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._bezier_curve = (1, 0, 1, 1)
        self._duration = 5
        self._value = 0.0
        self._min_value = 0.0
        self._max_value = 1.0
        self.max_overshoot_value = -1
        self._repeat = False

        self.bezier_curve = bezier_curve
        self.duration = duration
        self.value = min_value
        self.min_value = min_value
        self.max_value = max_value
        self.max_overshoot_value = max_overshoot_value
        self.repeat = repeat

        self.playing = False
        self._start_time = None
        self._tick_handler = None
        self._timeline_pos = 0
        self._tick_widget = tick_widget

    def do_get_time_now(self):
        return GLib.get_monotonic_time() / 1_000_000

    def do_lerp(self, start: float, end: float, time: float) -> float:
        return start + (end - start) * time

    def do_interpolate_cubic_bezier(self, time: float) -> float:
        x1, y1, x2, y2 = self.bezier_curve
        t = self.do_solve_bezier_x(x1, x2, time)
        mt = 1 - t
        return 3 * mt**2 * t * y1 + +3 * mt * t**2 * y2 + +(t**3)

    def do_solve_bezier_x(self, x1: float, x2: float, target_x: float) -> float:
        # solve for t where Bx(t) = target_x, using Newton-Raphson with bisection fallback
        def bx(t):
            mt = 1 - t
            return 3 * mt**2 * t * x1 + 3 * mt * t**2 * x2 + t**3

        def dbx(t):
            mt = 1 - t
            return 3 * mt**2 * x1 + 6 * mt * t * (x2 - x1) + 3 * t**2 * (1 - x2)

        t = target_x
        for _ in range(8):
            x_est = bx(t) - target_x
            d = dbx(t)
            if abs(d) < 1e-6:
                break
            t -= x_est / d
            t = min(max(t, 0.0), 1.0)
        return t

    def do_ease(self, time: float) -> float:
        y = self.do_interpolate_cubic_bezier(time)
        delta = self.max_value - self.min_value

        if abs(delta) < 1e-5:
            return self.max_value

        # normal
        if 0.0 <= y <= 1.0:
            return self.min_value + delta * y

        def dampen(raw_px: float, cap: float) -> float:
            if cap <= 0:
                return raw_px
            dist = abs(raw_px)
            damped_dist = (dist * cap) / (dist + cap)
            return damped_dist if raw_px > 0 else -damped_dist

        # overshoot
        if y > 1.0:
            raw_overshoot = delta * (y - 1.0)
            
            if self.max_overshoot_value == -1.0:
                return self.max_value + raw_overshoot
            elif self.max_overshoot_value == 0:
                return self.max_value
            else:
                return self.max_value + dampen(raw_overshoot, self.max_overshoot_value)

        # undershoot
        else: # y < 0.0
            raw_undershoot = delta * y
            
            if self.max_overshoot_value == -1.0:
                return self.min_value + raw_undershoot
            elif self.max_overshoot_value == 0:
                return self.min_value
            else:
                return self.min_value + dampen(raw_undershoot, self.max_overshoot_value)

    def do_update_value(self, delta_time: float):
        if not self.playing:
            return

        elapsed_time = delta_time - cast(float, self._start_time)
        self._timeline_pos = min(1, elapsed_time / self.duration)
        self.value = self.do_ease(self._timeline_pos)

        if not self._timeline_pos >= 1:
            return

        if not self.repeat:
            self.value = self.max_value
            self.finished()
            self.pause()
            return

        self._start_time = delta_time
        self._timeline_pos = 0
        return

    def do_handle_tick(self, *_):
        current_time = self.do_get_time_now()
        self.do_update_value(current_time)
        return True

    def do_remove_tick_handlers(self):
        if self._tick_handler:
            if self._tick_widget:
                self._tick_widget.remove_tick_callback(self._tick_handler)
            else:
                GLib.source_remove(self._tick_handler)
        self._tick_handler = None

    def play(self):
        if self.playing:
            return

        if self.duration == 0:
            self.value = self.max_value
            self.finished()
            return

        self._start_time = self.do_get_time_now()

        if not self._tick_handler:
            if self._tick_widget:
                self._tick_handler = self._tick_widget.add_tick_callback(
                    self.do_handle_tick
                )
            else:
                self._tick_handler = GLib.timeout_add(16, self.do_handle_tick)

        self.playing = True
        return

    def pause(self):
        self.playing = False
        return self.do_remove_tick_handlers()

    def stop(self):
        self.playing = False
        if not self._tick_handler:
            self._timeline_pos = 0
            return
        return self.do_remove_tick_handlers()
