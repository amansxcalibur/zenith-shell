import math
from collections.abc import Callable, Iterable

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore

from widgets.graphs import rounded_rect, theme_color


class PageTabs(Box):
    """Tab row with a pill that morphs between tabs.

    Each edge of the pill is its own spring, and the edge leading the movement is the
    stiffer one: the pill stretches towards the new tab, thins out while stretched,
    then the trailing edge catches up. Only ticks while moving.
    """

    LEADING_STIFFNESS = 520.0
    TRAILING_STIFFNESS = 220.0
    DAMPING_RATIO = 0.85  # just under critical: a small overshoot as it lands
    SQUISH = 0.05  # px of height lost, per px stretched beyond the resting width
    MAX_SQUISH = 4.0
    SETTLE_DISTANCE = 0.3
    SETTLE_SPEED = 5.0
    MAX_STEP = 1 / 30

    def __init__(
        self,
        pages: Iterable[tuple[str, Gtk.Widget, str]],
        on_change: Callable[[str], None],
        **kwargs,
    ):
        """`pages` is (page name, icon widget, title); `on_change` gets the page name."""
        super().__init__(spacing=2, **kwargs)
        self.buttons: dict[str, Button] = {}
        for name, icon, title in pages:
            button = Button(
                style_classes=["metrics-sort", "metrics-page-tab"],
                child=Box(spacing=5, children=[icon, Label(label=title)]),
                on_clicked=lambda _, page=name: on_change(page),
            )
            button.set_can_focus(False)
            self.buttons[name] = button
            self.add(button)

        self._active: str | None = None
        self._animated = True
        self._tick_id = None
        self._last_frame = None
        self._left = self._right = 0.0
        self._left_speed = self._right_speed = 0.0

        self.connect("draw", self._on_draw)  # runs first, so the pill is under the tabs
        self.connect("size-allocate", self._on_size_allocate)
        self.connect("unmap", lambda *_: self._stop_moving())

    @property
    def active(self) -> str | None:
        return self._active

    def set_animated(self, animated: bool) -> None:
        self._animated = animated
        if not animated:
            self._stop_moving()

    def set_page(self, name: str) -> None:
        self._active = name
        for page, button in self.buttons.items():
            context = button.get_style_context()
            (context.add_class if page == name else context.remove_class)("active")

        if self._animated and self.get_mapped():
            if self._tick_id is None:
                self._last_frame = None
                self._tick_id = self.add_tick_callback(self._tick)
        else:
            self._stop_moving()

    def _target(self) -> tuple[float, float]:
        if self._active is None:
            return 0.0, 0.0
        button = self.buttons[self._active].get_allocation()
        x = button.x - self.get_allocation().x
        return float(x), float(x + button.width)

    def _on_size_allocate(self, *_) -> None:
        if self._tick_id is None:
            self._left, self._right = self._target()

    def _stop_moving(self) -> None:
        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None
        self._left, self._right = self._target()
        self._left_speed = self._right_speed = 0.0
        self.queue_draw()

    def _tick(self, widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time() / 1_000_000
        dt = now - self._last_frame if self._last_frame else 0.0
        self._last_frame = now
        moving = self.step(min(dt, self.MAX_STEP))
        self.queue_draw()
        if not moving:
            self._tick_id = None
        return moving

    def step(self, dt: float) -> bool:
        """Advance the springs by `dt` seconds; returns whether they're still moving."""
        target_left, target_right = self._target()
        moving_right = target_left > self._left

        self._left, self._left_speed = self._spring(
            self._left,
            self._left_speed,
            target_left,
            self.TRAILING_STIFFNESS if moving_right else self.LEADING_STIFFNESS,
            dt,
        )
        self._right, self._right_speed = self._spring(
            self._right,
            self._right_speed,
            target_right,
            self.LEADING_STIFFNESS if moving_right else self.TRAILING_STIFFNESS,
            dt,
        )

        settled = all(
            abs(position - target) < self.SETTLE_DISTANCE
            and abs(speed) < self.SETTLE_SPEED
            for position, target, speed in (
                (self._left, target_left, self._left_speed),
                (self._right, target_right, self._right_speed),
            )
        )
        if settled:
            self._left, self._right = target_left, target_right
            self._left_speed = self._right_speed = 0.0
        return not settled

    def _spring(
        self, position: float, speed: float, target: float, stiffness: float, dt: float
    ) -> tuple[float, float]:
        damping = 2 * self.DAMPING_RATIO * math.sqrt(stiffness)
        speed += ((target - position) * stiffness - speed * damping) * dt
        return position + speed * dt, speed

    def _on_draw(self, widget, cr) -> bool:
        if self._active is None:
            return False
        height = self.get_allocated_height()
        target_left, target_right = self._target()

        # cairo clips to this box, so keep an overshoot from flattening against its ends
        left = max(0.0, self._left)
        right = min(float(self.get_allocated_width()), self._right)
        stretch = max(0.0, (right - left) - (target_right - target_left))
        inset = min(self.MAX_SQUISH, stretch * self.SQUISH)

        Gdk.cairo_set_source_rgba(cr, theme_color(self, "primary"))
        rounded_rect(cr, left, inset, right - left, height - 2 * inset, height / 2)
        cr.fill()
        return False
