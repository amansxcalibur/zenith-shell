import math
import cairo
from loguru import logger

from widgets.shapes.base import Shape

class Pill(Shape):

    def _draw_circle(self, ctx: cairo.Context, cx: float, cy: float, radius: float):
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.close_path()
        ctx.fill_preserve()
        ctx.stroke()

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        base_radius = min(width, height) / 2.35

        ctx.set_source_rgb(*self._get_color())
        ctx.set_line_width(0)

        # top circle
        top_cx, top_cy = width - base_radius, base_radius
        self._draw_circle(ctx, top_cx, top_cy, base_radius)

        # connecting line
        ctx.set_line_width(2 * base_radius)
        ctx.move_to(top_cx, top_cy)
        ctx.line_to(base_radius, width - base_radius)
        ctx.stroke()

        # bottom circle
        ctx.set_line_width(0)
        bottom_cx, bottom_cy = base_radius, width - base_radius
        self._draw_circle(ctx, bottom_cx, bottom_cy, base_radius)

        return True