import math
from expressive_shapes.shapes import *

from fabric.widgets.box import Box

from widgets.elastic.rotate_box import RotateBox
from widgets.shapes.expressive.morphing_shapes import AnimateShapeMorph


class MaterialExpressiveLoader(Box):
    @property
    def is_running(self) -> bool:
        return self._is_running

    def __init__(self, size: int = 150, **kwargs):
        self.loader_size = size
        self.inner_size = int(size / math.sqrt(2))

        self.shape = AnimateShapeMorph(
            name="shape",
            presets=[
                circle,
                oval,
                pill,
                very_sunny,
                sunny,
                cookie_4,
                cookie_12,
                leaf_clover_4,
                boom,
                bun,
            ],
        )

        self.rotater = RotateBox(
            h_expand=True,
            v_expand=True,
            child=Box(
                name="shape-container",
                h_expand=True,
                v_expand=True,
                all_visible=True,
                children=self.shape,
                size=self.inner_size,
            ),
        )
        self.rotater.show_all()

        super().__init__(
            h_expand=True,
            v_expand=True,
            size=self.loader_size,
            children=self.rotater,
            h_align="center",
            v_align="center",
            all_visible=True,
            **kwargs,
        )

        self.cruise_speed = 40.0  # degrees / second
        self.morph_speed = 320.0
        # higher = snappier response when the target speed changes
        self.speed_smoothing = 18.0

        self._angle_deg = 0.0
        self._current_speed = self.cruise_speed
        self._last_time = 0.0

        self._is_running = False
        self._tick_id = None

        self.start()

    def start(self):
        if self._is_running:
            return

        self._is_running = True
        self._last_time = 0.0  # Reset so the first frame calculates dt correctly

        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._on_tick)

    def stop(self, reset_position: bool = False):
        if not self._is_running and not reset_position:
            return

        self._is_running = False

        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None

        if reset_position:
            self.reset()

    def reset(self):
        self._angle_deg = 0.0
        self.rotater.angle = 0.0
        self._current_speed = self.cruise_speed
        self.shape.reset()

    def _on_tick(self, widget, frame_clock):
        if not self._is_running:
            self._tick_id = None
            return False

        now = frame_clock.get_frame_time()

        if self._last_time == 0.0:
            self._last_time = now
            return True

        dt = (now - self._last_time) / 1_000_000.0
        self._last_time = now

        # lag spike protection
        dt = min(dt, 0.1)

        is_morphing = self.shape.current_pause_time <= 0

        target_speed = self.morph_speed if is_morphing else self.cruise_speed

        # exponential smoothing towards target speed
        blend = 1 - math.pow(math.e, -self.speed_smoothing * dt)
        self._current_speed += (target_speed - self._current_speed) * blend

        self._angle_deg = (self._angle_deg + self._current_speed * dt) % 360
        self.rotater.angle = self._angle_deg

        return True
