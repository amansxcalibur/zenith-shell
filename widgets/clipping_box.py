import math
import cairo
from typing import cast
from fabric.widgets.box import Box
from services.animator import Animator
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


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
        return self.do_get_preferred_height()

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
        bezier_curve: tuple[float, float, float, float] = (0.42, 0, 0.58, 1),
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._revealed = True if self._max_height == -1 else False

        self.set_valign(Gtk.Align.START)

        self.animator = Animator(
            bezier_curve=bezier_curve,
            duration=duration,
            tick_widget=self,
        )
        self.animator.connect("notify::value", self._on_animation_tick)

    def _on_animation_tick(self, animator: Animator, _pspec) -> None:
        self.set_max_height(int(animator.value))

    def _animate(self, from_height: int, to_height: int) -> None:
        self.animator.pause()
        self.animator.min_value = from_height
        self.animator.max_value = to_height
        self.animator.play()

    def toggle(self, collapsed_height: int = _COLLAPSED_HEIGHT_DEFAULT) -> None:
        if self._revealed:
            self.collapse(collapsed_height)
        else:
            self.expand()

    def expand(self, target_height: int| None = None) -> None:
        if self._revealed:
            return
        self._revealed = True

        if target_height is None:
            _, natural_height = Box.do_get_preferred_height(self)
        else:
            natural_height = target_height
        self._animate(self.get_allocated_height(), natural_height)

        # once animation settles, lift the constraint entirely
        # so future child resizes are never clipped
        def _on_done(anim, _pspec):
            if not anim.playing:
                self.clear_max_height()
                anim.disconnect(handler)

        handler = self.animator.connect("notify::playing", _on_done)

    def collapse(self, target_height: int = _COLLAPSED_HEIGHT_DEFAULT) -> None:
        if not self._revealed:
            return
        self._revealed = False

        self._max_height = self.get_allocated_height()
        self._animate(self.get_allocated_height(), target_height)

    def refresh(self) -> None:
        # only meaningful when collapsed
        if self._revealed:
            return
        _, natural_height = Box.do_get_preferred_height(self)
        self._animate(self.get_allocated_height(), natural_height)
