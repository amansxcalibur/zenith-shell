import math
from loguru import logger

from widgets.shapes.base import Shape

class WavyCircle(Shape):
    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        cx, cy = width / 2, height / 2

        base_radius = min(width, height) * 0.45
        amplitude = base_radius * 0.05
        frequency = 10

        # wavy outer circle
        ctx.set_line_width(4)
        angle_step = 2 * math.pi / 500
        ctx.move_to(
            cx + (base_radius + amplitude * math.sin(frequency * 0)) * math.cos(0),
            cy + (base_radius + amplitude * math.sin(frequency * 0)) * math.sin(0),
        )

        angle = 0
        while angle <= math.tau:
            r = base_radius + amplitude * math.sin(frequency * angle)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            ctx.line_to(x, y)
            angle += angle_step

        ctx.set_source_rgb(*self._get_color())

        ctx.close_path()
        ctx.fill_preserve()
        ctx.stroke()

        return True