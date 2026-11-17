from fabric.core.service import Service, Property

from collections.abc import Callable
from enum import Enum, auto

from fabric.widgets.box import Box

from services.animator import Animator, CubicBezierCurves
from widgets.clipping_box import TrueClippingBox
from config.config import config

from services.power_profiles import power_profiles_service


def motion_scale() -> float:
    return 0.5 if power_profiles_service.active_profile == "power-saver" else 1.0


class Motion(Enum):
    ENTER = auto()
    EXIT = auto()


class CollapsingBox(Box):
    """Basically an AnimatedClippingBox going between 0 and its natural height
    with a fade, except the content is laid out at full size and cut off while
    it shrinks, instead of being squeezed into the smaller box."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._anim_height: int | None = None  # forced height while animating
        self._natural = 0  # content height used for layout while animating
        self._mode: Motion | None = None  # None = at rest
        self._animator: Animator | None = None
        self._run_from = 0
        self._run_to = 0
        self._run_opacity = 1.0
        self._on_done: Callable[[], None] | None = None

    @property
    def exiting(self) -> bool:
        return self._mode == Motion.EXIT

    def do_get_preferred_height(self) -> tuple[int, int]:
        if self._anim_height is not None:
            return self._anim_height, self._anim_height
        return Box.do_get_preferred_height(self)

    def do_get_preferred_height_for_width(self, width: int) -> tuple[int, int]:
        if self._anim_height is not None:
            return self._anim_height, self._anim_height
        return Box.do_get_preferred_height_for_width(self, width)

    def do_size_allocate(self, allocation) -> None:
        if self._anim_height is None:
            return Box.do_size_allocate(self, allocation)
        # lay the content out at its natural height, then set our own
        # allocation to the animated one; do_draw clips the overflow
        full = allocation.copy()
        full.height = max(allocation.height, self._natural)
        Box.do_size_allocate(self, full)
        self.set_allocation(allocation)

    def do_draw(self, cr) -> bool:
        if self._anim_height is None:
            return Box.do_draw(self, cr)
        radius = self.get_style_context().get_property(
            "border-radius", self.get_state_flags()
        )
        cr.save()
        TrueClippingBox._rounded_rect(
            cr, self.get_allocated_width(), self.get_allocated_height(), radius
        )
        cr.clip()
        Box.do_draw(self, cr)
        cr.restore()
        return True

    def _set_anim_height(self, value: int) -> None:
        if value != self._anim_height:
            self._anim_height = value
            self.queue_resize()

    def _get_animator(self) -> Animator:
        if self._animator is None:
            self._animator = Animator(
                bezier_curve=CubicBezierCurves.EMPHASIS,
                duration=0.3,
                tick_widget=self,
            )
            self._animator.connect("notify::value", self._on_tick)
            self._animator.connect("finished", self._on_finished)
        return self._animator

    def _run(self, curve, duration: float, start: int, end: int, overshoot: float):
        self._run_from, self._run_to = start, end
        animator = self._get_animator()
        animator.pause()  # play() is a no-op while playing
        animator.bezier_curve = curve
        animator.duration = duration
        animator.max_overshoot_value = overshoot
        animator.min_value = start
        animator.max_value = end
        animator.value = start
        animator.play()

    def _on_tick(self, animator: Animator, _pspec) -> None:
        value = max(0, round(animator.value))
        if self._mode == Motion.ENTER:
            self.set_opacity(max(0.0, min(1.0, value / self._run_to * 1.5)))
        elif self._mode == Motion.EXIT:
            # fade tracks the height and finishes at 20% left, so it stays
            # visible while it moves instead of vanishing up front
            fade = max(0.0, min(1.0, value / self._run_from * 1.25 - 0.25))
            self.set_opacity(self._run_opacity * fade)
        else:
            return
        self._set_anim_height(value)

    def _on_finished(self, _animator: Animator) -> None:
        if self._mode == Motion.ENTER:
            self._end_enter()
        elif self._mode == Motion.EXIT:
            on_done, self._on_done = self._on_done, None
            if on_done is not None:
                on_done()

    def _stop(self) -> None:
        if self._animator is not None:
            self._animator.pause()

    def animate_enter(self, duration: float = 0.4) -> None:
        if self._mode is not None:
            return
        duration *= motion_scale()
        self._mode = Motion.ENTER
        self.set_opacity(0.0)
        self._set_anim_height(0)

        def _start(*_) -> bool:
            if self._mode != Motion.ENTER:
                return False
            width = self.get_allocated_width()
            if width <= 1:
                return True  # not laid out yet
            target = Box.do_get_preferred_height_for_width(self, width)[1]
            if target <= 0:
                self._end_enter()
                return False
            self._natural = target
            # small, damped bounce (px)
            self._run(CubicBezierCurves.EXPRESSIVE, duration, 0, target, 8)
            return False

        self.add_tick_callback(_start)

    def _end_enter(self) -> None:
        if self._mode != Motion.ENTER:
            return
        self._mode = None
        self.set_opacity(1.0)
        self._anim_height = None
        self.queue_resize()

    def animate_exit(self, on_done: Callable[[], None], duration: float = 0.35) -> None:
        if self._mode == Motion.EXIT:
            return
        duration *= motion_scale()
        entering = self._mode == Motion.ENTER
        self._stop()  # an exit can interrupt an enter mid-way
        height = (
            self._anim_height
            if entering and self._anim_height is not None
            else self.get_allocated_height()
        )
        self._mode = Motion.EXIT
        if height <= 1 or not self.get_mapped():
            on_done()
            return

        if not entering:
            self._natural = height
        self._set_anim_height(height)
        self._run_opacity = self.get_opacity()
        self._on_done = on_done
        self._run(CubicBezierCurves.STANDARD, duration, height, 0, -1.0)


class NotificationConfig:
    WIDTH = 360
    MAX_CHARS_PER_LINE = 27
    MAX_CHARS_PER_COLLAPSED_LINE = 38
    LINE_LIMIT = 3
    IMAGE_SIZE = 48
    TIMEOUT = 5 * 1000  # 5 seconds
    TRANSITION_DURATION = 250
    REVEALER_TRANSITION_TYPE = "slide-down"
    MAX_ACTIVE_NOTIFS = 2
    WINDOW_MIN_HEIGHT = 10
    WINDOW_MIN_WIDTH = 364
    WINDOW_MAX_HEIGHT = 700
    WINDOW_MAX_WIDTH = 1900
    SPACING = 3
    MARGIN = 3
    IMAGE_BORDER_RADIUS = 18
    SNAP_THRESHOLD = 50
    SILENT = config.SILENT


class NotificationNotifier(Service):
    _instance = None

    @Property(bool, default_value=False, flags="read-write")
    def has_unread(self) -> bool:
        return self._has_unread

    @has_unread.setter
    def has_unread(self, value: bool) -> None:
        self._has_unread = value

    @Property(bool, default_value=False, flags="read-write")
    def has_urgent_unread(self) -> bool:
        return self._has_urgent_unread

    @has_urgent_unread.setter
    def has_urgent_unread(self, value: bool) -> None:
        self._has_urgent_unread = value

    @Property(bool, default_value=False, flags="read-write")
    def silent(self) -> bool:
        return self._silent

    @silent.setter
    def silent(self, value: bool) -> None:
        self._silent = value
        config.SILENT = value

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()
        self._initialized = True

        self._has_unread = False
        self._has_urgent_unread = False
        self._silent = config.SILENT
