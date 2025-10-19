from typing import Tuple
import math
import cairo
import datetime

import config.info as info
from utils.colors import get_css_variable, hex_to_rgb01

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


class WavyClock(Gtk.DrawingArea):
    def __init__(self, size: Tuple[int, int] = (-1, 140), dark: True = False):
        super().__init__()
        self.set_size_request(size[0], size[1])
        self.connect("draw", self.on_draw)

        GLib.timeout_add_seconds(1, self.on_tick)

        self.show()

    def on_tick(self):
        self.queue_draw()
        return True

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

        hex_color = get_css_variable(
            f"{info.HOME_DIR}/fabric/styles/colors.css", "--primary"
        )
        r, g, b = hex_to_rgb01(hex_color)
        ctx.set_source_rgb(r, g, b)

        ctx.close_path()
        ctx.fill_preserve()
        ctx.set_source_rgb(r, g, b)
        ctx.stroke()

        ANGLE_OFFSET = 0.25
        now = datetime.datetime.now()
        seconds = now.second + now.microsecond / 1e6
        hour = now.hour % 12 + now.minute / 60.0
        minute = now.minute + now.second / 60.0

        second_angle = (seconds / 60.0 - ANGLE_OFFSET) * math.tau
        hour_angle = (hour / 12.0 - ANGLE_OFFSET) * math.tau
        minute_angle = (minute / 60.0 - ANGLE_OFFSET) * math.tau

        dot_radius = int(width / 18)  # 7
        hour_orbit = base_radius * 0.8 - dot_radius * 4
        minute_orbit = base_radius * 0.8 - dot_radius * 2
        second_orbit = base_radius * 0.8

        ctx.set_line_cap(cairo.LINE_CAP_ROUND)  # rounded line ends

        # hour hand
        hr_r, hr_g, hr_b = hex_to_rgb01(
            get_css_variable(
                f"{info.HOME_DIR}/fabric/styles/colors.css", "--on-primary"
            )
        )
        ctx.set_line_width(dot_radius*2)
        ctx.set_source_rgba(hr_r, hr_g, hr_b, 0.6)
        ctx.move_to(cx, cy)
        ctx.line_to(
            cx + hour_orbit * math.cos(hour_angle),
            cy + hour_orbit * math.sin(hour_angle),
        )
        ctx.stroke()

        # minute hand
        ctx.set_line_width(dot_radius*2)
        ctx.set_source_rgba(hr_r, hr_g, hr_b, 1)
        ctx.move_to(cx, cy)
        ctx.line_to(
            cx + minute_orbit * math.cos(minute_angle),
            cy + minute_orbit * math.sin(minute_angle),
        )
        ctx.stroke()

        # inner orbiting second dot
        # dot_radius = int(width / 17) # 9
        x = cx + second_orbit * math.cos(second_angle)
        y = cy + second_orbit * math.sin(second_angle)

        ctx.arc(x, y, dot_radius, 0, math.tau)
        hex_color = get_css_variable(
            f"{info.HOME_DIR}/fabric/styles/colors.css", "--tertiary"
        )
        r, g, b = hex_to_rgb01(hex_color)
        ctx.set_source_rgba(r, g, b)
        ctx.fill()
