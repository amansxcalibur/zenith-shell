import math
import cairo
from loguru import logger

from widgets.shapes.base import Shape

class Circle(Shape):
    def _draw_circle(self, ctx: cairo.Context, cx: float, cy: float, radius: float):
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.close_path()
        ctx.fill_preserve()
        ctx.stroke()

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        base_radius = min(width, height)/2

        ctx.set_source_rgb(*self._get_color())
        ctx.set_line_width(0)

        # top circle
        self._draw_circle(ctx, base_radius, base_radius, base_radius)

        return True