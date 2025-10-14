import math
from loguru import logger

from widgets.shapes.base import Shape


class Ellipse(Shape):
    def path_ellipse(self, ctx, x, y, width, height, angle=0):
        # x, y   - centers
        # width  - width of ellipse  (in x direction when angle=0)
        # height - height of ellipse (in y direction when angle=0)
        # angle  - angle in radians to rotate, clockwise
        
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(angle)
        ctx.scale(width / 2.0, height / 2.0)
        ctx.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
        ctx.restore()


    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        ctx.scale(width, height)
        ctx.set_line_width(0)

        # 1 x 1 scaled to width x height
        self.path_ellipse(ctx, 0.5, 0.5, 1.0, 0.6, -math.pi / 4)

        ctx.set_source_rgb(*self._get_color())
        ctx.fill_preserve()

        # reset identity matrix so line_width is a constant
        # width in device-space, not user-space
        ctx.save()
        ctx.identity_matrix()
        ctx.restore()

        return True