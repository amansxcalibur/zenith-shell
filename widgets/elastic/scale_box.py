import cairo
from loguru import logger
from typing import Literal
from collections.abc import Callable, Iterable

from fabric.core.service import Property

from services.animator import Animator
from .rotate_box import RotateBox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib # type: ignore


class ScaleBox(RotateBox):
    """
    Wraps an arbitrary child widget and renders it at a scaled size.
    The offscreen window holds the child at its natural size; the
    main window is sized to natural * scale.  Hit-testing is handled
    by inverting the same matrix used for drawing.
    """

    @Property(float, "read-write", default_value=1.0)
    def scale_x(self) -> float:
        return self._scale_x

    @scale_x.setter
    def scale_x(self, value: float):
        self._scale_x = max(value, 0.001)
        self.queue_resize()
        if self._offscreen_window:
            self._offscreen_window.geometry_changed()

    @Property(float, "read-write", default_value=1.0)
    def scale_y(self) -> float:
        return self._scale_y

    @scale_y.setter
    def scale_y(self, value: float):
        self._scale_y = max(value, 0.001)
        self.queue_resize()
        if self._offscreen_window:
            self._offscreen_window.geometry_changed()

    def __init__(
        self,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        child: Gtk.Widget | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        self._scale_x = max(scale_x, 0.01)
        self._scale_y = max(scale_y, 0.01)
        self._child = None
        self._offscreen_window = None
        self._shrink_source_id: int | None = None

        super().__init__(
            clip=False,
            angle=0.0,
            child=child,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            style_classes=style_classes,
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            size=size,
            **kwargs,
        )

        self.show_all()

    def do_bake_transformation(self) -> cairo.Matrix:
        m = cairo.Matrix()
        m.scale(self._scale_x, self._scale_y)
        return m

    def do_get_preferred_width(self) -> tuple[int, int]:
        if not self._child:
            return 0, 0
        min_w, nat_w = self._child.get_preferred_width()
        return (
            max(1, int(min_w * self._scale_x)),
            max(1, int(nat_w * self._scale_x)),
        )

    def do_get_preferred_height(self) -> tuple[int, int]:
        if not self._child:
            return 0, 0
        min_h, nat_h = self._child.get_preferred_height()
        return (
            max(1, int(min_h * self._scale_y)),
            max(1, int(nat_h * self._scale_y)),
        )

    def do_size_allocate(self, allocation: cairo.RectangleInt):
        # main window -> scaled
        # offscreen -> natural
        self.set_allocation(allocation)
        bw = self.get_border_width()

        win_w = allocation.width - bw * 2
        win_h = allocation.height - bw * 2

        if self.get_realized():
            self.get_window().move_resize(
                allocation.x + bw, allocation.y + bw, win_w, win_h
            )

        if not self._child or not self._child.get_visible():
            return

        # child always lives at its natural size in the offscreen window
        _, nat = self._child.get_preferred_size()
        child_w, child_h = nat.width, nat.height

        child_alloc: cairo.RectangleInt = Gdk.Rectangle()  # type: ignore
        child_alloc.x = 0
        child_alloc.y = 0
        child_alloc.width = child_w
        child_alloc.height = child_h

        if self._offscreen_window and self.get_realized():
            self._ensure_offscreen_capacity(child_w, child_h)

        self._child.size_allocate(child_alloc)

    # offscreen surface management
    # Resizing a GdkOffscreenWindow destroys and recreates its backing surface
    # and invalidates all of it. With a size-interpolating child (e.g. a Gtk.Stack
    # with interpolate_size=True) the natural size changes on every frame, so an
    # exact-fit surface would be reallocated + fully repainted every frame.
    # Instead the surface grows geometrically and only shrinks back to an exact
    # fit once the child's size has been stable for a moment.

    _GROWTH_FACTOR = 1.5
    _SHRINK_DELAY_MS = 500

    def _ensure_offscreen_capacity(self, need_w: int, need_h: int):
        win = self._offscreen_window
        cap_w, cap_h = win.get_width(), win.get_height()

        if need_w > cap_w or need_h > cap_h:
            new_w = max(need_w, int(cap_w * self._GROWTH_FACTOR)) if need_w > cap_w else cap_w
            new_h = max(need_h, int(cap_h * self._GROWTH_FACTOR)) if need_h > cap_h else cap_h
            win.move_resize(0, 0, new_w, new_h)
            cap_w, cap_h = new_w, new_h

        if (need_w, need_h) != (cap_w, cap_h):
            self._schedule_offscreen_shrink()
        else:
            self._cancel_offscreen_shrink()

    def _schedule_offscreen_shrink(self):
        # restart the timer on every size change, so we only shrink once settled
        self._cancel_offscreen_shrink()
        self._shrink_source_id = GLib.timeout_add(
            self._SHRINK_DELAY_MS, self._shrink_offscreen_to_fit
        )

    def _cancel_offscreen_shrink(self):
        if self._shrink_source_id is not None:
            GLib.source_remove(self._shrink_source_id)
            self._shrink_source_id = None

    def _shrink_offscreen_to_fit(self):
        self._shrink_source_id = None
        if not (self._offscreen_window and self.get_realized() and self._child):
            return False
        alloc = self._child.get_allocation()
        w, h = max(alloc.width, 1), max(alloc.height, 1)
        win = self._offscreen_window
        if (win.get_width(), win.get_height()) != (w, h):
            win.move_resize(0, 0, w, h)
        return False

    def do_unrealize(self):
        self._cancel_offscreen_shrink()
        return RotateBox.do_unrealize(self)


class AnimatedScaleBox(ScaleBox):
    def __init__(
        self,
        scale: float = 1.0,
        child: Gtk.Widget | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        super().__init__(
            scale_x=scale,
            scale_y=scale,
            child=child,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            style_classes=style_classes,
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            size=size,
            **kwargs,
        )

        self._animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.3,
            min_value=scale,
            max_value=scale,
            tick_widget=self,
        )
        self._animator.connect("notify::value", self._on_animator_value)
        self._done_handler_id: int | None = None 

    def _on_animator_value(self, animator: Animator, _):
        v = animator.value
        # avoid redundant resize cycles
        if abs(v - self._scale_x) > 1e-6:
            self._scale_x = v
            self._scale_y = v
            self.queue_resize()
            if self._offscreen_window:
                self._offscreen_window.geometry_changed()

    def animate_to(
        self,
        target: float,
        duration: float = 0.3,
        bezier: tuple[float, float, float, float] = (0.4, 0.0, 0.2, 1.0),
        on_done: Callable | None = None,
    ):
        start = self._scale_x  # snapshot before pause()

        self._animator.pause()

        # disconnect previous one-shot finished handler
        if self._done_handler_id is not None:
            try:
                self._animator.disconnect(self._done_handler_id)
            except Exception as e:
                logger.error(f"Failed to disconnect animator {e}")
            self._done_handler_id = None

        self._animator.min_value = start
        self._animator.max_value = target
        self._animator.duration = duration
        self._animator.bezier_curve = bezier
        self._animator.value = start

        if on_done is not None:
            def _on_finished(_):
                self._animator.disconnect(self._done_handler_id)
                self._done_handler_id = None
                on_done()

            self._done_handler_id = self._animator.connect("finished", _on_finished)

        self._animator.play()
