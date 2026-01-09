import gi
import math
import cairo

from fabric.widgets.scale import Scale
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.utils.helpers import clamp

from services.animator import Animator

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, GObject


class AnimatedScale(Scale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = (
            Animator(
                bezier_curve=(0.15, 0.88, 0.68, 0.95),
                duration=0.3,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
            .build()
            .play()
            .unwrap()
        )

    def animate_value(self, value: float):
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()
        return


class CircularScale(CircularProgressBar):
    NON_ROUND_CAP_DELTA = 0.01

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # gadgets
        self.trough_ctx = self.do_create_gadget_context("trough")
        self.slider_ctx = self.do_create_gadget_context("slider")
        self.highlight_ctx = self.do_create_gadget_context("highlight")

    def do_get_thickness_from_context(self, context, state):
        border = context.get_border(state)
        return max(
            self._line_width,
            border.top,
            border.bottom,
            border.left,
            border.right,
            context.get_property("min-width", state),
            context.get_property("min-height", state),
        )

    def do_calculate_safe_radius(
        self, delta, slider_height, progress_thickness, trough_thickness
    ):
        max_thickness = max(slider_height, progress_thickness, trough_thickness)
        return max(delta - max_thickness / 2, 0)

    def do_normalize_value(self):
        value_range = self._max_value - self._min_value
        if value_range == 0:
            return 0.0
        return clamp((self._value - self._min_value) / value_range, 0.0, 1.0)

    def do_get_arc_delta(self):
        # add a tiny delta to force the rendering of line caps. (square and butt)
        return self.NON_ROUND_CAP_DELTA if self.line_style != cairo.LineCap.ROUND else 0

    def do_draw_progress_arc(
        self,
        cr,
        center_x,
        center_y,
        safe_radius,
        start_angle,
        progress_thickness,
        progress_angle,
        progress_color,
        progress_line_width_angle,
        slider_thickness_angle,
        left_gap_angle,
    ):
        cr.set_line_width(progress_thickness)
        Gdk.cairo_set_source_rgba(cr, progress_color)

        if progress_angle - progress_line_width_angle - left_gap_angle > start_angle:
            # draw normal arc
            arc_start = (
                start_angle + (progress_line_width_angle - slider_thickness_angle) / 2
            )
            arc_end = (
                progress_angle
                - (progress_line_width_angle / 2 + slider_thickness_angle / 2)
                - left_gap_angle
            )
            cr.arc(center_x, center_y, safe_radius, arc_start, arc_end)
            cr.stroke()
        else:
            # draw shrinking dot when available space is minimal
            ratio = progress_line_width_angle / (
                progress_line_width_angle + left_gap_angle
            )
            dot_arc = (
                -(
                    start_angle
                    - slider_thickness_angle / 2
                    - (progress_angle - slider_thickness_angle / 2)
                )
                / 2
                * ratio
            )
            dot_radius = 2 * safe_radius * math.sin(dot_arc)

            cr.set_line_width(dot_radius)
            true_start = start_angle - slider_thickness_angle / 2 + dot_arc
            delta = self.do_get_arc_delta()
            cr.arc(center_x, center_y, safe_radius, true_start, true_start + delta)
            cr.stroke()
            cr.set_line_width(safe_radius * progress_line_width_angle)

    def do_draw_slider(
        self,
        cr,
        center_x,
        center_y,
        safe_radius,
        progress_angle,
        slider_color,
        slider_thickness_angle,
        slider_height,
        corner_radius,
    ):
        angle_rad = progress_angle
        sx = center_x + math.cos(angle_rad) * safe_radius
        sy = center_y + math.sin(angle_rad) * safe_radius

        cr.save()
        cr.translate(sx, sy)
        cr.rotate(angle_rad + math.pi / 2)

        Gdk.cairo_set_source_rgba(cr, slider_color)

        self.do_draw_rounded_rect(
            cr,
            -(slider_thickness_angle * safe_radius) / 2,
            -slider_height / 2,
            slider_thickness_angle * safe_radius,
            slider_height,
            corner_radius,
        )
        cr.fill()
        cr.restore()

    def do_draw_trough_arc(
        self,
        cr,
        center_x,
        center_y,
        safe_radius,
        progress_angle,
        real_end_angle,
        trough_color,
        trough_thickness,
        trough_line_width_angle,
        slider_thickness_angle,
        right_gap_angle,
    ):
        cr.set_line_width(trough_thickness)
        Gdk.cairo_set_source_rgba(cr, trough_color)

        remaining_start = (
            progress_angle + trough_line_width_angle / 2 + slider_thickness_angle / 2
        )
        remaining_end = (
            real_end_angle - slider_thickness_angle / 2 - trough_line_width_angle / 2
        )

        if remaining_start < remaining_end - right_gap_angle:
            # draw arc
            cr.arc(
                center_x,
                center_y,
                safe_radius,
                remaining_start + right_gap_angle,
                remaining_end,
            )
            cr.stroke()
        else:
            # draw shrinking dot when remaining space is minimal
            ratio = trough_line_width_angle / (
                trough_line_width_angle + right_gap_angle
            )
            true_end = real_end_angle - slider_thickness_angle / 2
            remaining_angle = true_end - (progress_angle + slider_thickness_angle / 2)
            remaining_usable_angle = max(remaining_angle, 0.0) * ratio

            chord_length = 2 * safe_radius * math.sin(remaining_usable_angle / 2)
            cr.set_line_width(chord_length)

            mid_angle = (
                progress_angle
                + slider_thickness_angle / 2
                + remaining_angle * (1 - ratio)
                + remaining_usable_angle / 2
            )
            delta = self.do_get_arc_delta()
            cr.arc(center_x, center_y, safe_radius, mid_angle, mid_angle + delta)
            cr.stroke()

    def do_draw(self, cr: cairo.Context):
        state = self.get_state_flags()
        style_context = self.get_style_context()

        border = style_context.get_border(state)
        background_color = style_context.get_background_color(state)

        width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_x = width / 2
        center_y = height / 2

        # slider properties
        slider_color = self.slider_ctx.get_background_color(state)
        slider_height = self.slider_ctx.get_property("min-height", state)
        slider_thickness = self.slider_ctx.get_property("min-width", state)
        left_gap = self.slider_ctx.get_property("margin-left", state)
        right_gap = self.slider_ctx.get_property("margin-right", state)
        corner_radius = self.slider_ctx.get_property("border-radius", state)

        # progress (highlight) properties
        progress_color = self.highlight_ctx.get_background_color(state)
        progress_thickness = self.do_get_thickness_from_context(
            self.highlight_ctx, state
        )

        # trough properties
        trough_color = self.trough_ctx.get_background_color(state)
        trough_thickness = self.do_get_thickness_from_context(self.trough_ctx, state)

        # calculate radius
        radius = self.do_calculate_radius()
        safe_radius = self.do_calculate_safe_radius(
            radius, slider_height, progress_thickness, trough_thickness
        )
        if safe_radius == 0:
            if child := self.get_child():
                self.propagate_draw(child, cr)
            return

        cr.save()
        cr.set_line_cap(self._line_style)

        # background fill
        cr.set_line_width(0)
        Gdk.cairo_set_source_rgba(cr, background_color)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # angles (S = r*theta)
        left_gap_angle = left_gap / safe_radius
        right_gap_angle = right_gap / safe_radius
        progress_line_width_angle = progress_thickness / safe_radius
        trough_line_width_angle = trough_thickness / safe_radius
        slider_thickness_angle = slider_thickness / safe_radius

        start_angle = math.radians(self._start_angle)
        end_angle = (
            math.radians(self._end_angle) - slider_thickness_angle - right_gap_angle
        )
        real_end_angle = math.radians(self._end_angle) - right_gap_angle

        normalized_value = self.do_normalize_value()
        progress_angle = start_angle + normalized_value * (end_angle - start_angle)

        # exposed for override
        self.do_draw_progress_arc(
            cr=cr,
            center_x=center_x,
            center_y=center_y,
            safe_radius=safe_radius,
            start_angle=start_angle,
            progress_angle=progress_angle,
            progress_color=progress_color,
            progress_thickness=progress_thickness,
            progress_line_width_angle=progress_line_width_angle,
            slider_thickness_angle=slider_thickness_angle,
            left_gap_angle=left_gap_angle,
        )

        self.do_draw_slider(
            cr=cr,
            center_x=center_x,
            center_y=center_y,
            safe_radius=safe_radius,
            progress_angle=progress_angle,
            slider_color=slider_color,
            slider_thickness_angle=slider_thickness_angle,
            slider_height=slider_height,
            corner_radius=corner_radius,
        )

        self.do_draw_trough_arc(
            cr=cr,
            center_x=center_x,
            center_y=center_y,
            safe_radius=safe_radius,
            progress_angle=progress_angle,
            real_end_angle=real_end_angle,
            trough_color=trough_color,
            trough_thickness=trough_thickness,
            trough_line_width_angle=trough_line_width_angle,
            slider_thickness_angle=slider_thickness_angle,
            right_gap_angle=right_gap_angle,
        )

        # draw child (if any)
        if child := self.get_child():
            self.propagate_draw(child, cr)

        cr.restore()
        return False

    def do_create_gadget_context(self, node_name):
        ctx = Gtk.StyleContext()
        ctx.set_parent(self.get_style_context())

        path = self.get_style_context().get_path().copy()
        path.append_type(GObject.TYPE_NONE)
        path.iter_set_object_name(-1, node_name)

        ctx.connect("changed", lambda _: self.queue_draw())
        ctx.set_path(path)
        return ctx

    def do_draw_rounded_rect(self, cr, x, y, width, height, radius):
        if isinstance(radius, (int, float)):
            rtl = rtr = rbr = rbl = float(radius)
        else:
            rtl, rtr, rbr, rbl = map(float, radius)

        rtl, rtr, rbr, rbl = [max(0.0, v) for v in [rtl, rtr, rbr, rbl]]

        # for scaling down overflowing corner radius
        factor = 1.0

        # top edge
        if (rtl + rtr) > width:
            factor = min(factor, width / (rtl + rtr))
        # bottom edge
        if (rbl + rbr) > width:
            factor = min(factor, width / (rbl + rbr))
        # left edge
        if (rtl + rbl) > height:
            factor = min(factor, height / (rtl + rbl))
        # right edge
        if (rtr + rbr) > height:
            factor = min(factor, height / (rtr + rbr))

        if factor < 1.0:
            rtl *= factor
            rtr *= factor
            rbr *= factor
            rbl *= factor

        cr.new_sub_path()

        if rtl == rtr == rbr == rbl == 0:
            cr.rectangle(x, y, width, height)
            return

        # top-left (after the corner curve)
        cr.move_to(x + rtl, y)

        # top edge & top-right corner
        cr.line_to(x + width - rtr, y)
        if rtr > 0:
            cr.arc(x + width - rtr, y + rtr, rtr, -math.pi / 2, 0)

        # right edge & bottom-right corner
        cr.line_to(x + width, y + height - rbr)
        if rbr > 0:
            cr.arc(x + width - rbr, y + height - rbr, rbr, 0, math.pi / 2)

        # bottom edge & bottom-left corner
        cr.line_to(x + rbl, y + height)
        if rbl > 0:
            cr.arc(x + rbl, y + height - rbl, rbl, math.pi / 2, math.pi)

        # left edge & top-left corner
        cr.line_to(x, y + rtl)
        if rtl > 0:
            cr.arc(x + rtl, y + rtl, rtl, math.pi, 3 * math.pi / 2)

        cr.close_path()


class AnimatedCircularScale(CircularScale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = (
            Animator(
                bezier_curve=(0.15, 0.88, 0.68, 0.95),
                duration=0.8,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
            .build()
            .play()
            .unwrap()
        )

    def animate_value(self, value: float):
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()
        return


class WigglyCircularScale(AnimatedCircularScale):
    def __init__(self, frequency: int = 12, **kwargs):
        super().__init__(**kwargs)

        self.frequency = frequency

    def do_draw_progress_arc(
        self,
        cr,
        center_x,
        center_y,
        safe_radius,
        start_angle,
        progress_thickness,
        progress_angle,
        progress_color,
        progress_line_width_angle,
        slider_thickness_angle,
        left_gap_angle,
    ):
        cr.set_line_width(progress_thickness)
        Gdk.cairo_set_source_rgba(cr, progress_color)

        if progress_angle - progress_line_width_angle - left_gap_angle > start_angle:
            # draw normal arc
            arc_start = (
                start_angle + (progress_line_width_angle - slider_thickness_angle) / 2
            )
            arc_end = (
                progress_angle
                - (progress_line_width_angle / 2 + slider_thickness_angle / 2)
                - left_gap_angle
            )
            # cr.arc(center_x, center_y, safe_radius, arc_start, arc_end)
            self.circular_sine_path(
                cr=cr,
                cx=center_x,
                cy=center_y,
                base_radius=safe_radius,
                start_angle=arc_start,
                end_angle=arc_end,
                amplitude=progress_thickness * 0.25,
                frequency=self.frequency,
                phase=0.0,
                steps=300,
            )
            cr.stroke()
        else:
            # draw shrinking dot when available space is minimal
            ratio = progress_line_width_angle / (
                progress_line_width_angle + left_gap_angle
            )
            dot_arc = (
                -(
                    start_angle
                    - slider_thickness_angle / 2
                    - (progress_angle - slider_thickness_angle / 2)
                )
                / 2
                * ratio
            )
            dot_radius = 2 * safe_radius * math.sin(dot_arc)

            cr.set_line_width(dot_radius)
            true_start = start_angle - slider_thickness_angle / 2 + dot_arc
            delta = self.do_get_arc_delta()
            cr.arc(center_x, center_y, safe_radius, true_start, true_start + delta)
            cr.stroke()
            cr.set_line_width(safe_radius * progress_line_width_angle)

    def circular_sine_path(
        self,
        cr,
        cx,
        cy,
        base_radius,
        start_angle,
        end_angle,
        amplitude,
        frequency,
        phase=0.0,
        steps=200,
    ):
        total = end_angle - start_angle
        cr.new_path()

        for i in range(steps + 1):
            t = i / steps
            theta = start_angle + total * t

            wobble = amplitude * math.sin(frequency * (theta - start_angle) + phase)

            r = base_radius + wobble
            x = cx + math.cos(theta) * r
            y = cy + math.sin(theta) * r

            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
