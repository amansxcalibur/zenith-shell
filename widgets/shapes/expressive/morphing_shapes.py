import cairo
import threading
from typing import Literal, Iterable

from expressive_shapes.morph.bezier_morph import Morph
from expressive_shapes.geometry.rounded_polygon import RoundedPolygon
from expressive_shapes.shapes.shape_presets import (
    fan,
    gem,
    bun,
    pill,
    star,
    oval,
    arch,
    boom,
    heart,
    arrow,
    sunny,
    flower,
    shield,
    circle,
    square,
    slanted,
    diamond,
    triangle,
    pentagon,
    cookie_4,
    cookie_8,
    clamshell,
    ghost_ish,
    cookie_12,
    very_sunny,
    semicircle,
    pixel_circle,
    organic_blob,
    leaf_clover_4,
    leaf_clover_8,
    puffy_diamond,
    pixel_triangle,
)

from fabric.widgets.container import Container

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


class ExpressiveShape(Gtk.Bin, Container):
    def __init__(
        self,
        shape=circle,
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
        Gtk.DrawingArea.__init__(self)  # type: ignore
        Container.__init__(
            self,
            child,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.polygon = self.create_rounded_polygon(shape)

        self.connect("draw", self.on_draw)

        self.show_all()

    def create_rounded_polygon(self, unit_data) -> RoundedPolygon:
        verts = []
        per_vertex = []
        for (ux, uy), rounding_preset in unit_data:
            verts.extend([ux, uy])
            per_vertex.append(rounding_preset)

        return RoundedPolygon.create(vertices=verts, per_vertex_rounding=per_vertex)

    def on_draw(self, widget, ctx: cairo.Context):
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        style_context = self.get_style_context()
        state = self.get_state_flags()
        background_color = style_context.get_background_color(state)

        ctx.save()

        Gdk.cairo_set_source_rgba(ctx, background_color)

        side = min(width, height)
        ctx.translate((width - side) / 2, (height - side) / 2)
        scale_factor = side
        ctx.scale(scale_factor, scale_factor)

        curves = self.polygon.get_all_curves()

        if not curves:
            return False

        ctx.move_to(curves[0].p0.x, curves[0].p0.y)

        for c in curves:
            # ctx.curve_to(control1_x, control1_y, control2_x, control2_y, end_x, end_y)
            ctx.curve_to(c.p1.x, c.p1.y, c.p2.x, c.p2.y, c.p3.x, c.p3.y)

        ctx.close_path()

        ctx.set_line_width(1 / scale_factor)
        ctx.stroke_preserve()

        ctx.fill()

        if child := self.get_child():
            self.propagate_draw(child, ctx)

        ctx.restore()

        return False


# this is mainly for debugging
class BezierShapeMorph(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.alpha = 0.0
        self.direction = 1
        self.step_once = False

        poly_start = self.create_rounded_polygon(square)
        poly_end = self.create_rounded_polygon(fan)

        self.mappings = Morph.match(poly_start, poly_end)

        self.connect("draw", self.on_draw)

        GLib.timeout_add(16, self.update_animation)

        threading.Thread(target=self.wait_for_enter, daemon=True).start()
        self.show_all()

    def wait_for_enter(self):
        while True:
            input()
            GLib.idle_add(self._trigger_step)

    def _trigger_step(self):
        self.step_once = True
        return False  # run once

    def update_animation(self):
        if not self.step_once:
            return True

        self.step_once = False

        # step = 0.032 * self.direction
        step = 0.1 * self.direction
        self.alpha += step

        if self.alpha >= 1.0:
            self.alpha = 1.0
            self.direction = -1
        elif self.alpha <= 0.0:
            self.alpha = 0.0
            self.direction = 1

        self.queue_draw()
        return True

    def create_rounded_polygon(self, unit_data):
        verts = []
        per_vertex = []
        for (ux, uy), rounding_preset in unit_data:
            verts.extend([ux, uy])
            per_vertex.append(rounding_preset)

        return RoundedPolygon.create(vertices=verts, per_vertex_rounding=per_vertex)

    def on_draw(self, widget, ctx: cairo.Context):
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        side = min(width, height)
        ctx.translate((width - side) / 2, (height - side) / 2)
        scale_factor = side
        ctx.scale(scale_factor, scale_factor)

        curves = Morph.as_cubics(self.mappings, self.alpha)

        if not curves:
            return False

        ctx.move_to(curves[0].p0.x, curves[0].p0.y)

        for c in curves:
            # ctx.curve_to(control1_x, control1_y, control2_x, control2_y, end_x, end_y)
            ctx.curve_to(c.p1.x, c.p1.y, c.p2.x, c.p2.y, c.p3.x, c.p3.y)

        ctx.close_path()

        ctx.set_source_rgb(0.4, 0.6, 0.9)
        ctx.set_line_width(1 / scale_factor)
        ctx.stroke_preserve()

        ctx.set_source_rgba(0.4, 0.6, 0.9, 0.0)
        ctx.fill()

        # # --- debug dots ---
        # dot_radius = 6
        # for c in curves:
        #     # anchors (p0, p3), control points (p1, p2)
        #     pts = [(c.p0, True), (c.p1, False), (c.p2, False), (c.p3, True)]

        #     for pt, is_anchor in pts:
        #         if is_anchor:
        #             ctx.set_source_rgb(0.0, 0.4, 1.0)  # Deep Blue
        #             ctx.arc(pt.x, pt.y, dot_radius, 0, 2 * math.pi)
        #             ctx.fill()
        #         else:
        #             ctx.set_source_rgba(0.0, 0.8, 1.0, 0.7)  # Translucent Cyan
        #             ctx.arc(pt.x, pt.y, dot_radius, 0, 2 * math.pi)
        #             ctx.stroke()

        #     # draw lines connecting handles to anchors
        #     ctx.set_source_rgba(0.5, 0.5, 0.5, 0.5)
        #     ctx.set_line_width(2)
        #     ctx.move_to(c.p0.x, c.p0.y)
        #     ctx.line_to(c.p1.x, c.p1.y)
        #     ctx.move_to(c.p3.x, c.p3.y)
        #     ctx.line_to(c.p2.x, c.p2.y)
        #     ctx.stroke()

        # ctx.set_source_rgb(1.0, 0.0, 0.5)  # Material Pink
        # for i in range(0, len(verts), 2):
        #     vx, vy = verts[i], verts[i + 1]
        #     ctx.arc(vx, vy, dot_radius + 2, 0, 2 * math.pi)
        #     ctx.fill()

        return False


class AnimateShapeMorph(Gtk.DrawingArea):
    def __init__(self, name: str):
        super().__init__(name=name)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.presets = [
            circle,
            square,
            slanted,
            arch,
            semicircle,
            oval,
            pill,
            triangle,
            arrow,
            fan,
            diamond,
            clamshell,
            pentagon,
            gem,
            very_sunny,
            sunny,
            cookie_4,
            cookie_8,
            cookie_12,
            leaf_clover_4,
            leaf_clover_8,
            boom,
            puffy_diamond,
            flower,
            ghost_ish,
            pixel_circle,
            pixel_triangle,
            bun,
            heart,
            organic_blob,
            shield,
        ]
        self.current_idx = 0

        self.progress = 0.0
        self.animation_speed = 0.032
        self.pause_frames = 20
        self.pause_counter = 0

        self._prepare_next_morph()

        self.connect("draw", self.on_draw)
        GLib.timeout_add(16, self.update_animation)  # ~60 fps
        self.show_all()

    def _prepare_next_morph(self):
        next_idx = (self.current_idx + 1) % len(self.presets)

        poly_start = self.create_rounded_polygon(self.presets[self.current_idx])
        poly_end = self.create_rounded_polygon(self.presets[next_idx])

        self.mappings = Morph.match(poly_start, poly_end)

    @staticmethod
    def _cubic_bezier(x1, y1, x2, y2):
        def _sample_x(t):
            return 3.0 * x1 * t * (1 - t) ** 2 + 3.0 * x2 * t**2 * (1 - t) + t**3

        def _sample_y(t):
            return 3.0 * y1 * t * (1 - t) ** 2 + 3.0 * y2 * t**2 * (1 - t) + t**3

        def _dx_dt(t):
            return (
                3.0 * x1 * (1 - t) ** 2
                + 6.0 * (x2 - x1) * t * (1 - t)
                + 3.0 * (1 - x2) * t**2
            )

        def easing(x):
            if x <= 0.0:
                return 0.0
            if x >= 1.0:
                return 1.0

            # Newton-Raphson: solve _sample_x(t) = x for t
            t = x  # initial guess
            for _ in range(8):
                dx = _dx_dt(t)
                if abs(dx) < 1e-12:
                    break
                t -= (_sample_x(t) - x) / dx
                t = max(0.0, min(1.0, t))

            # Bisection fallback if Newton didn't converge
            if abs(_sample_x(t) - x) > 1e-6:
                lo, hi = 0.0, 1.0
                for _ in range(20):
                    t = (lo + hi) / 2.0
                    if _sample_x(t) < x:
                        lo = t
                    else:
                        hi = t

            return _sample_y(t)

        return easing

    def material_easing(self, t):
        if not hasattr(self, "_m3_ease_in"):
            self._m3_ease_in = self._cubic_bezier(0.05, 0.0, 0.133333, 0.06)
            self._m3_ease_out = self._cubic_bezier(0.208333, 0.82, 0.25, 1.0)

        if t < 0.4:
            return self._m3_ease_in(t / 0.4) * 0.2
        else:
            return 0.2 + self._m3_ease_out((t - 0.4) / 0.6) * 0.8

    def update_animation(self):
        # handle the pause between shapes
        if self.pause_counter > 0:
            self.pause_counter -= 1
            return True

        self.progress += self.animation_speed

        if self.progress >= 1.0:
            self.progress = 0.0
            self.current_idx = (self.current_idx + 1) % len(self.presets)
            self.pause_counter = self.pause_frames
            self._prepare_next_morph()

        self.queue_draw()
        return True

    def create_rounded_polygon(self, unit_data):
        verts = []
        per_vertex = []
        for (ux, uy), rounding_preset in unit_data:
            verts.extend([ux, uy])
            per_vertex.append(rounding_preset)

        return RoundedPolygon.create(vertices=verts, per_vertex_rounding=per_vertex)

    def on_draw(self, widget, ctx: cairo.Context):
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        style_context = self.get_style_context()
        state = self.get_state_flags()
        background_color = style_context.get_background_color(state)

        Gdk.cairo_set_source_rgba(ctx, background_color)

        side = min(width, height)
        ctx.translate((width - side) / 2, (height - side) / 2)
        scale_factor = side
        ctx.scale(scale_factor, scale_factor)

        alpha = self.material_easing(self.progress)

        curves = Morph.as_cubics(self.mappings, alpha)
        if not curves:
            return False

        ctx.move_to(curves[0].p0.x, curves[0].p0.y)
        for c in curves:
            ctx.curve_to(c.p1.x, c.p1.y, c.p2.x, c.p2.y, c.p3.x, c.p3.y)

        ctx.close_path()

        ctx.set_line_width(0)
        ctx.stroke_preserve()

        ctx.fill()

        return False
