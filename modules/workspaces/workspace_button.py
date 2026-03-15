import cairo
from typing import Literal
from random import randrange
from collections.abc import Iterable

from expressive_shapes.morph.bezier_morph import Morph
from expressive_shapes.geometry.rounded_polygon import RoundedPolygon
from expressive_shapes.shapes.shape_presets import (
    organic_blob,
    pill,
    shield,
    cookie_12,
    cookie_8,
    fan,
    flower,
    arrow,
    leaf_clover_4,
    circle,
    square,
    slanted,
    arch,
    semicircle,
    oval,
    triangle,
    diamond,
    clamshell,
    pentagon,
    gem,
    very_sunny,
    sunny,
    cookie_4,
    puffy_diamond,
    ghost_ish,
    pixel_triangle,
    bun,
    heart,
    pixel_circle,
    boom,
    leaf_clover_8,
    FULL_ROUND,
)


from fabric.widgets.box import Box
from fabric.widgets.button import Button

# from fabric.widgets.overlay import Overlay
from fabric.core.service import Property
from fabric.utils.helpers import FormattedString
from fabric.i3.widgets import WorkspaceButton as FabricWorkspaceButton

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


class WorkspaceShapeMorph(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(name="workspace-morph-shape")
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.active_shapes = [
            boom,
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

        # small circle shape
        P = 0.28
        self._non_active_shape = [
            ((0.10 + P, 0.10 + P), FULL_ROUND),
            ((0.90 - P, 0.10 + P), FULL_ROUND),
            ((0.90 - P, 0.90 - P), FULL_ROUND),
            ((0.10 + P, 0.90 - P), FULL_ROUND),
        ]
        self.current_idx = 0

        self.progress = 0.0
        self.animation_speed = 0.082
        self.pause_frames = 20
        self.pause_counter = 0
        self.glib_id = None

        self._prepare_next_morph()

        self.connect("draw", self.on_draw)
        self.show_all()

    def _prepare_next_morph(self):
        self.current_idx = randrange(len(self.active_shapes))

        poly_start = self.create_rounded_polygon(self._non_active_shape)
        poly_end = self.create_rounded_polygon(self.active_shapes[self.current_idx])

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

    def update_animation(self, positive_direction: bool = True):
        self.progress += self.animation_speed * (+1 if positive_direction else -1)

        if self.progress >= 1.0 or self.progress <= 0.0:
            self.progress = max(0.0, min(1.0, self.progress))  # clamp
            self.glib_id = None
            return False

        self.queue_draw()
        return True

    def morph_active(self):
        # already in active state
        if self.progress >= 1:
            return

        # morph from 0.0 to 1.0
        elif self.progress <= 0:
            self.progress = 0.0
            self._prepare_next_morph()
            if self.glib_id is not None:
                GLib.source_remove(self.glib_id)
            self.glib_id = GLib.timeout_add(16, self.update_animation)  # ~60 fps

        # morph to 1.0 with the same active shape
        else:
            if self.glib_id is not None:
                GLib.source_remove(self.glib_id)
            self.glib_id = GLib.timeout_add(16, self.update_animation, True)  # ~60 fps

    def morph_deactivate(self):
        # already in deactive state
        if self.progress <= 0:
            return

        # morph to 0.0
        else:
            if self.progress > 1:
                self.progress = 1.0

            if self.glib_id is not None:
                GLib.source_remove(self.glib_id)
            self.glib_id = GLib.timeout_add(16, self.update_animation, False)  # ~60 fps

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


class WorkspaceButton(FabricWorkspaceButton):
    @FabricWorkspaceButton.active.setter
    def active(self, value: bool):
        self._active = value
        self.handle_activate(value)
        self._update_style_class("active", value)
        return self.do_bake_label()

    @FabricWorkspaceButton.urgent.setter
    def urgent(self, value: bool):
        self._urgent = value
        self._update_style_class("urgent", value)
        return self.do_bake_label()

    @FabricWorkspaceButton.empty.setter
    def empty(self, value: bool):
        self._empty = value
        self._update_style_class("empty", value)
        return self.do_bake_label()

    def __init__(
        self,
        id: int,
        label: FormattedString | str | None = None,
        image: Gtk.Image | None = None,
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
        self.morphing_shape = WorkspaceShapeMorph()
        self.morphing_shape.morph_deactivate()

        super().__init__(
            id,
            label,
            image,
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

        # TODO
        # self.bg_box = Box(
        #     name="ws-btn-background-box",
        #     h_expand=True,
        # )

        self.children = (
            Box(
                h_expand=True,
                children=[
                    Box(
                        h_expand=True,
                        style="padding:2px",
                        children=self.morphing_shape,
                    ),
                    # TODO
                    # Overlay(
                    #     h_expand=True,
                    #     child=Box(children=self.bg_box),
                    #     overlays=Box(
                    #         h_expand=True,
                    #         style="padding:2px",
                    #         children=self.morphing_shape,
                    #     ),
                    # )
                ],
            ),
        )

    def _update_style_class(self, class_name: str, value: bool):
        context = self.morphing_shape.get_style_context()

        if value:
            context.add_class(class_name)
            self.add_style_class(class_name)
        else:
            context.remove_class(class_name)
            self.remove_style_class(class_name)

    def handle_activate(self, value: bool):
        if value:
            self.morphing_shape.morph_active()
        else:
            self.morphing_shape.morph_deactivate()

    def do_bake_label(self):
        if not self._label:
            return
        return self.set_label(self._label.format(button=self))
