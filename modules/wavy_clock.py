import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from utils.colors import get_css_variable, hex_to_rgb01
import config.info as info

import math

class WavyCircle(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.connect("draw", self.on_draw)

        # internal ticking dot angle
        self.dot_angle = 0
        self.set_size_request(-1, 153)

        GLib.timeout_add_seconds(1, self.on_tick)

    def on_tick(self):
        self.dot_angle += math.tau / 60
        self.dot_angle %= math.tau
        self.queue_draw()
        return True

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        cx, cy = width / 2, height / 2

        base_radius = min(width, height) * 0.4
        amplitude = base_radius * 0.06
        frequency = 10

        # wavy outer circle
        ctx.set_line_width(4)
        angle_step = 2 * math.pi / 500
        ctx.move_to(
            cx + (base_radius + amplitude * math.sin(frequency * 0)) * math.cos(0),
            cy + (base_radius + amplitude * math.sin(frequency * 0)) * math.sin(0)
        )

        angle = 0
        while angle <= math.tau:
            r = base_radius + amplitude * math.sin(frequency * angle)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            ctx.line_to(x, y)
            angle += angle_step

        hex_color = get_css_variable(f'{info.HOME_DIR}/fabric/styles/colors.css', '--primary')
        r, g, b = hex_to_rgb01(hex_color)
        ctx.set_source_rgb(r, g, b)

        ctx.close_path()
        ctx.fill_preserve()
        hex_color = get_css_variable(f'{info.HOME_DIR}/fabric/styles/colors.css', '--primary')
        r, g, b = hex_to_rgb01(hex_color)
        ctx.set_source_rgb(r, g, b)
        ctx.stroke()

        # inner orbiting dot
        dot_radius = 9
        orbit_radius = base_radius * 0.7

        x = cx + orbit_radius * math.cos(self.dot_angle)
        y = cy + orbit_radius * math.sin(self.dot_angle)

        ctx.arc(x, y, dot_radius, 0, math.tau)
        hex_color = get_css_variable(f'{info.HOME_DIR}/fabric/styles/colors.css', '--on-primary')
        r, g, b = hex_to_rgb01(hex_color)
        ctx.set_source_rgba(r, g, b)
        ctx.fill()
