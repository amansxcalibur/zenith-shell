import math
import cairo
from typing import cast
from collections.abc import Callable
from fabric.widgets.box import Box
from services.animator import Animator, CubicBezierCurves
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


class ClippingBox(Box):
    """A regular `Box` that replicates the CSS behaviour of `overflow: hidden` because GTK failed at it."""

    @staticmethod
    def render_shape(cr: cairo.Context, width: int, height: int, radius: int = 0):
        radius = max(0, min(radius, width / 2, height / 2))

        if radius == 0:
            cr.rectangle(0, 0, width, height)
            return

        cr.move_to(radius, 0)
        cr.line_to(width - radius, 0)
        cr.arc(width - radius, radius, radius, -(math.pi / 2), 0)
        cr.line_to(width, height - radius)
        cr.arc(width - radius, height - radius, radius, 0, (math.pi / 2))
        cr.line_to(radius, height)
        cr.arc(radius, height - radius, radius, (math.pi / 2), math.pi)
        cr.line_to(0, radius)
        cr.arc(radius, radius, radius, math.pi, (3 * (math.pi / 2)))

        return cr.close_path()

    def do_draw(self, cr: cairo.Context):
        cr.save()
        ClippingBox.render_shape(
            cr,
            self.get_allocated_width(),
            self.get_allocated_height(),
            cast(
                int,
                self.get_style_context().get_property(
                    "border-radius", self.get_state_flags()
                ),
            ),
        )
        cr.clip()

        Box.do_draw(self, cr)

        cr.restore()
        return True


class TrueClippingBox(Box):
    """Adds max-height/width support"""

    def __init__(self, max_width: int = -1, max_height: int = -1, **kwargs):
        super().__init__(**kwargs)
        self._max_height = max_height  # -1 = no limit
        self._max_width = max_width  # -1 = no limit

    @staticmethod
    def _rounded_rect(cr: cairo.Context, width: int, height: int, radius: int) -> None:
        radius = max(0, min(radius, width / 2, height / 2))

        if radius == 0:
            cr.rectangle(0, 0, width, height)
            return

        PI = math.pi
        cr.move_to(radius, 0)
        cr.line_to(width - radius, 0)
        cr.arc(width - radius, radius, radius, -PI / 2, 0)
        cr.line_to(width, height - radius)
        cr.arc(width - radius, height - radius, radius, 0, PI / 2)
        cr.line_to(radius, height)
        cr.arc(radius, height - radius, radius, PI / 2, PI)
        cr.line_to(0, radius)
        cr.arc(radius, radius, radius, PI, 3 * PI / 2)
        cr.close_path()

    @staticmethod
    def render_shape(
        cr: cairo.Context, width: int, height: int, radius: int = 0
    ) -> None:
        TrueClippingBox._rounded_rect(cr, width, height, radius)

    def _clamp_w(self, value: int) -> int:
        return min(value, self._max_width) if self._max_width != -1 else value

    def _clamp_h(self, value: int) -> int:
        return min(value, self._max_height) if self._max_height != -1 else value

    def do_get_preferred_width(self) -> tuple[int, int]:
        minimum, natural = Box.do_get_preferred_width(self)
        return self._clamp_w(minimum), self._clamp_w(natural)

    def do_get_preferred_height(self) -> tuple[int, int]:
        minimum, natural = Box.do_get_preferred_height(self)
        return self._clamp_h(minimum), self._clamp_h(natural)

    def do_get_preferred_height_for_width(self, width: int) -> tuple[int, int]:
        minimum, natural = Box.do_get_preferred_height_for_width(self, width)
        return self._clamp_h(minimum), self._clamp_h(natural)

    def do_size_allocate(self, allocation) -> None:
        alloc = allocation.copy()
        if self._max_width != -1:
            alloc.width = min(alloc.width, self._max_width)
        if self._max_height != -1:
            alloc.height = min(alloc.height, self._max_height)
        Box.do_size_allocate(self, alloc)

    def do_draw(self, cr: cairo.Context) -> bool:
        radius = self.get_style_context().get_property(
            "border-radius", self.get_state_flags()
        )
        cr.save()
        self._rounded_rect(
            cr, self.get_allocated_width(), self.get_allocated_height(), radius
        )
        cr.clip()
        Box.do_draw(self, cr)
        cr.restore()
        return True

    def set_max_width(self, width: int) -> None:
        self._max_width = width
        self.queue_resize()

    def set_max_height(self, height: int) -> None:
        self._max_height = height
        self.queue_resize()

    def clear_max_width(self) -> None:
        self._max_width = -1
        self.queue_resize()

    def clear_max_height(self) -> None:
        self._max_height = -1
        self.queue_resize()

    def clear_max_constraints(self) -> None:
        self._max_height = -1
        self._max_width = -1
        self.queue_resize()


class AnimatedClippingBox(TrueClippingBox):
    _COLLAPSED_HEIGHT_DEFAULT = 44

    @property
    def duration(self) -> float:
        return self.animator.duration

    @duration.setter
    def duration(self, value: float) -> None:
        self.animator.duration = value

    def __init__(
        self,
        duration: float = 0.25,
        contracting_bezier_curve: tuple[
            float, float, float, float
        ] = CubicBezierCurves.EXPRESSIVE,
        expanding_bezier_curve: tuple[
            float, float, float, float
        ] = CubicBezierCurves.EMPHASIS,
        max_overshoot_value: float = -1.0,
        fixed_height_animation: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._revealed = self._max_height == -1
        self._contracting_bezier_curve = contracting_bezier_curve
        self._expanding_bezier_curve = expanding_bezier_curve
        # fixed_height_animation: while animating, the box takes exactly the animated
        # height (instead of only being capped by it). Content that is shorter than
        # the animated height can't cut the motion short, so the curve (including
        # overshoot) plays out in full. Off by default to keep the old behaviour.
        self._fixed_height_animation = fixed_height_animation
        self._forced_height: int | None = None
        self._finish_handler: int | None = None
        # current animation (fixed_height_animation): start height, target (a
        # number or a callable re-read every frame) and the target's initial value
        self._anim_from = 0
        self._anim_target: int | Callable[[], int] = 0
        self._anim_estimate = 0

        self.set_valign(Gtk.Align.START)

        self.animator = Animator(
            bezier_curve=contracting_bezier_curve,
            duration=duration,
            tick_widget=self,
            max_overshoot_value=max_overshoot_value,
        )
        self.animator.connect("notify::value", self._on_animation_tick)

    # forced height (fixed_height_animation)
    def do_get_preferred_height(self) -> tuple[int, int]:
        if self._forced_height is not None:
            return self._forced_height, self._forced_height
        return TrueClippingBox.do_get_preferred_height(self)

    def do_get_preferred_height_for_width(self, width: int) -> tuple[int, int]:
        if self._forced_height is not None:
            return self._forced_height, self._forced_height
        return TrueClippingBox.do_get_preferred_height_for_width(self, width)

    def do_size_allocate(self, allocation) -> None:
        if self._forced_height is None:
            return TrueClippingBox.do_size_allocate(self, allocation)
        alloc = allocation.copy()
        if self._max_width != -1:
            alloc.width = min(alloc.width, self._max_width)
        alloc.height = self._forced_height
        Box.do_size_allocate(self, alloc)

    def hold(self) -> None:
        """Freeze the box at its current height until the next animation starts
        (lets the content change state without the box jumping in between)."""
        if not self._fixed_height_animation:
            return
        # stop a running animation: it would keep driving the height during the
        # hold, and its completion step belongs to the state being left
        self._disconnect_finish_handler()
        self.animator.pause()
        self._forced_height = self.get_allocated_height()
        self.queue_resize()

    def release_hold(self) -> None:
        if self._forced_height is None:
            return
        self._forced_height = None
        self.queue_resize()

    @staticmethod
    def _resolve(target: int | Callable[[], int]) -> int:
        return int(target()) if callable(target) else int(target)

    def _on_animation_tick(self, animator: Animator, _pspec) -> None:
        if not self._fixed_height_animation:
            self.set_max_height(max(0, int(animator.value)))
            return

        # the animator runs in pixels between the start height and the target's
        # initial value (so overshoot damping keeps its pixel meaning); turn that
        # into eased progress and apply it to the *live* target. Content that is
        # still settling (e.g. CSS size transitions) then can't leave a jump at
        # the end: at progress 1 the height is exactly the real target.
        span = self._anim_estimate - self._anim_from
        progress = 1.0 if span == 0 else (animator.value - self._anim_from) / span
        target = self._resolve(self._anim_target)
        value = max(0, round(self._anim_from + (target - self._anim_from) * progress))
        if value != self._forced_height:
            self._forced_height = value
            self.queue_resize()

    def _disconnect_finish_handler(self) -> None:
        if self._finish_handler is not None:
            self.animator.disconnect(self._finish_handler)
            self._finish_handler = None

    def _animate(
        self, from_height: int, to_height: int | Callable[[], int], on_done=None
    ) -> None:
        # drop the previous animation's completion handler: an interrupted expand
        # must not run its "lift the clamp" step when the following collapse ends
        self._disconnect_finish_handler()
        self.animator.pause()
        estimate = self._resolve(to_height)
        self._anim_from = from_height
        self._anim_target = to_height
        self._anim_estimate = estimate
        self.animator.min_value = from_height
        self.animator.max_value = estimate

        def _done(_anim):
            self._disconnect_finish_handler()
            if on_done is not None:
                on_done()

        self._finish_handler = self.animator.connect("finished", _done)
        self.animator.play()

    def toggle(self, collapsed_height: int = _COLLAPSED_HEIGHT_DEFAULT) -> None:
        if self._revealed:
            self.collapse(collapsed_height)
        else:
            self.expand()

    def expand(self, target_height: int | Callable[[], int] | None = None) -> None:
        if self._revealed:
            return
        self._revealed = True
        self.animator.bezier_curve = self._expanding_bezier_curve

        if target_height is None:
            _, natural_height = Box.do_get_preferred_height(self)
        else:
            natural_height = target_height

        # once animation settles, lift the constraint entirely
        # so future child resizes are never clipped
        def _on_done():
            self._forced_height = None
            self.clear_max_height()

        self._animate(self.get_allocated_height(), natural_height, _on_done)

    def collapse(
        self, target_height: int | Callable[[], int] = _COLLAPSED_HEIGHT_DEFAULT
    ) -> None:
        if not self._revealed:
            return
        self._revealed = False
        self.animator.bezier_curve = self._contracting_bezier_curve

        self._max_height = self.get_allocated_height()

        def _on_done():
            if self._forced_height is not None:
                self._forced_height = None
                self.set_max_height(self._resolve(target_height))

        self._animate(self.get_allocated_height(), target_height, _on_done)

    def refresh(self) -> None:
        # only meaningful when collapsed
        if self._revealed:
            return
        _, natural_height = Box.do_get_preferred_height(self)

        def _on_done():
            if self._forced_height is not None:
                self._forced_height = None
                self.set_max_height(natural_height)

        self._animate(self.get_allocated_height(), natural_height, _on_done)


class OddlySpecificClippingBox(Box):
    """Adds per-corner clipping."""

    @staticmethod
    def render_shape(
        cr: cairo.Context, width: int, height: int, radii: list[int] | None = None
    ):
        if radii is None:
            radii = [0, 0, 0, 0]
        tl, tr, br, bl = radii

        max_allowed = min(width / 2, height / 2)
        tl = max(0, min(tl, max_allowed))
        tr = max(0, min(tr, max_allowed))
        br = max(0, min(br, max_allowed))
        bl = max(0, min(bl, max_allowed))

        if tl == 0 and tr == 0 and br == 0 and bl == 0:
            cr.rectangle(0, 0, width, height)
            return

        cr.move_to(tl, 0)
        cr.line_to(width - tr, 0)
        if tr > 0:
            cr.arc(width - tr, tr, tr, -(math.pi / 2), 0)
        else:
            cr.line_to(width, 0)

        cr.line_to(width, height - br)
        if br > 0:
            cr.arc(width - br, height - br, br, 0, (math.pi / 2))
        else:
            cr.line_to(width, height)

        cr.line_to(bl, height)
        if bl > 0:
            cr.arc(bl, height - bl, bl, (math.pi / 2), math.pi)
        else:
            cr.line_to(0, height)

        cr.line_to(0, tl)
        if tl > 0:
            cr.arc(tl, tl, tl, math.pi, (3 * (math.pi / 2)))
        else:
            cr.line_to(0, 0)

        return cr.close_path()

    def __init__(self, radii: list[int] | None = None, **kwargs):
        if radii is None:
            radii = [0, 0, 0, 0]
        self._radii = radii
        super().__init__(**kwargs)

    def do_draw(self, cr: cairo.Context):
        cr.save()
        OddlySpecificClippingBox.render_shape(
            cr,
            self.get_allocated_width(),
            self.get_allocated_height(),
            self._radii,
        )
        cr.clip()

        Box.do_draw(self, cr)

        cr.restore()
        return True
