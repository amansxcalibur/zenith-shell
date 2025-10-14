import math
from loguru import logger

from widgets.shapes.base import Shape

THETA = 105


class Pentagon(Shape):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.edge_radius = 0.3

    def path(self, ctx, x, y, radius=1):
        # Draw a pentagon inscribed in a smaller circle where r_outer-r_inner = distance from the inner circle's center
        # to the intersection point of its tangents (ie the sides of the larger pentagon inscribed inside the outer circle).
        # This way we can get the rounded corners without going through the hassle of drawing arcs.

        # regular pentagon points (unit size, centered at 0,0)
        pts = [
            (0.0, -0.5),
            (-0.4755, -0.1545),
            (-0.29475, 0.404),
            (0.29475, 0.404),
            (0.4755, -0.1545),
        ]

        r_outer = 1
        r_inner = r_outer - self.edge_radius / math.sin(THETA / 2)

        # scale points inward
        pts_inner = [(px / r_outer * r_inner, py / r_outer * r_inner) for px, py in pts]

        ctx.move_to(x + pts_inner[0][0] * radius, y + pts_inner[0][1] * radius)

        for px, py in pts_inner[1:]:
            ctx.line_to(x + px * radius, y + py * radius)
        ctx.close_path()

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        import cairo

        ctx.scale(width, height)  # normalize to 1x1 for convenience

        # rounded caps and joins - gives rounded edges
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        ctx.set_source_rgb(*self._get_color())

        self.path(ctx, 0.5, 0.5, 1)

        ctx.fill_preserve()

        ctx.set_line_width(self.edge_radius)
        ctx.stroke()

        return True
