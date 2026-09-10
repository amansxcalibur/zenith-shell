import math
import cairo
import datetime
from typing import ClassVar

from config.info import ROOT_DIR
from services.theme import ThemeService
from utils.colors import get_css_variable, hex_to_rgb01

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, GLib, Pango, PangoCairo  # type: ignore


class WavyClock(Gtk.DrawingArea):
    # geometry ratios, all relative to base_radius unless noted
    FILL_RATIO = 0.45  # base_radius as fraction of min(width, height)
    WAVE_AMPLITUDE_RATIO = 0.05
    WAVE_FREQUENCY = 12
    WAVE_SEGMENTS = 500
    ANGLE_OFFSET = 0.25  # rotates 12 o'clock to the top

    HAND_ORBIT_RATIO = 0.8  # shared base for hour/minute/second orbits
    HOUR_ORBIT_INSET = 4  # * dot_radius, subtracted from HAND_ORBIT_RATIO
    MINUTE_ORBIT_INSET = 2  # * dot_radius, subtracted from HAND_ORBIT_RATIO

    DOT_RADIUS_DIVISOR = 18  # dot_radius = width / this

    FONT_SIZE_RATIO = 0.18
    FONT_NAME = "Google Sans Flex"
    FONT_VARIATIONS: ClassVar = {"wght": 500, "ROND": 100, "wdth": 100}

    HOUR_HAND_ALPHA = 0.6
    MINUTE_HAND_ALPHA = 1.0
    TEXT_ALPHA = 0.8

    def __init__(self, size: tuple[int, int] = (-1, 160), dark: bool = False):
        super().__init__()
        self.dark = dark
        self.set_size_request(size[0], size[1])

        self.now = datetime.datetime.now()  # noqa: DTZ005

        # letter_spacing_factor: 1.0 = normal tracking, <1 = tighter, >1 = looser
        self.letter_spacing_factor = 1.0

        # cached, size-dependent draw state. Rebuilt lazily in on_draw only
        # when the allocation actually changes, not on every tick.
        self._cached_width = None
        self._cached_height = None
        self._base_radius = None
        self._font_desc = None
        self._dynamic_font_size_px = None

        self._load_theme_colors()
        self.theme_service = ThemeService()
        self.theme_service.connect(
            "colors-changed", lambda *_: self._load_theme_colors()
        )

        self.connect("draw", self.on_draw)

        GLib.timeout_add_seconds(1, self.on_tick)

        self.show()

    def _load_theme_colors(self):
        css_path = f"{ROOT_DIR}/styles/colors.css"
        self._primary_rgb = hex_to_rgb01(get_css_variable(css_path, "--primary"))
        self._on_primary_rgb = hex_to_rgb01(get_css_variable(css_path, "--on-primary"))
        self._tertiary_rgb = hex_to_rgb01(get_css_variable(css_path, "--tertiary"))
        self.queue_draw()

    def _ensure_size_dependent_state(self, width, height):
        if width == self._cached_width and height == self._cached_height:
            return

        self._cached_width = width
        self._cached_height = height
        self._base_radius = min(width, height) * self.FILL_RATIO

        dynamic_font_size_px = max(10, int(self._base_radius * self.FONT_SIZE_RATIO))
        if dynamic_font_size_px != self._dynamic_font_size_px:
            self._dynamic_font_size_px = dynamic_font_size_px
            font_desc = Pango.FontDescription.from_string(self.FONT_NAME)
            font_desc.set_size(dynamic_font_size_px * Pango.SCALE)
            variations = {**self.FONT_VARIATIONS, "opsz": dynamic_font_size_px}
            font_desc.set_variations(
                ",".join(f"{k}={v}" for k, v in variations.items())
            )
            self._font_desc = font_desc

    def on_tick(self):
        self.now = datetime.datetime.now()  # noqa: DTZ005
        self.queue_draw()
        return True

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        cx, cy = width / 2, height / 2

        self._ensure_size_dependent_state(width, height)
        base_radius = self._base_radius
        amplitude = base_radius * self.WAVE_AMPLITUDE_RATIO

        self._draw_wavy_circle(ctx, cx, cy, base_radius, amplitude)

        now = self.now
        seconds = now.second + now.microsecond / 1e6
        hour = now.hour % 12 + now.minute / 60.0
        minute = now.minute + now.second / 60.0

        second_angle = (seconds / 60.0 - self.ANGLE_OFFSET) * math.tau
        hour_angle = (hour / 12.0 - self.ANGLE_OFFSET) * math.tau
        minute_angle = (minute / 60.0 - self.ANGLE_OFFSET) * math.tau

        dot_radius = int(width / self.DOT_RADIUS_DIVISOR)
        hour_orbit = (
            base_radius * self.HAND_ORBIT_RATIO - dot_radius * self.HOUR_ORBIT_INSET
        )
        minute_orbit = (
            base_radius * self.HAND_ORBIT_RATIO - dot_radius * self.MINUTE_ORBIT_INSET
        )
        second_orbit = base_radius * self.HAND_ORBIT_RATIO

        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        self._draw_hand(
            ctx, cx, cy, hour_angle, hour_orbit, dot_radius, self.HOUR_HAND_ALPHA
        )
        self._draw_hand(
            ctx, cx, cy, minute_angle, minute_orbit, dot_radius, self.MINUTE_HAND_ALPHA
        )

        self._draw_second_dot(ctx, cx, cy, second_angle, second_orbit, dot_radius)
        self._draw_curved_date(ctx, cx, cy, second_angle, second_orbit, dot_radius)

    def _draw_wavy_circle(self, ctx, cx, cy, base_radius, amplitude):
        ctx.set_line_width(4)

        def wavy_radius(a):
            return base_radius + amplitude * math.cos(
                self.WAVE_FREQUENCY * (a + math.pi / 2)
            )

        r0 = wavy_radius(0)
        ctx.move_to(cx + r0, cy)

        for i in range(self.WAVE_SEGMENTS + 1):
            angle = (i / self.WAVE_SEGMENTS) * math.tau
            r = wavy_radius(angle)
            ctx.line_to(cx + r * math.cos(angle), cy + r * math.sin(angle))

        ctx.close_path()
        ctx.set_source_rgb(*self._primary_rgb)
        ctx.fill()

    def _draw_hand(self, ctx, cx, cy, angle, orbit, dot_radius, alpha):
        ctx.set_line_width(dot_radius * 2)
        ctx.set_source_rgba(*self._on_primary_rgb, alpha)
        ctx.move_to(cx, cy)
        ctx.line_to(cx + orbit * math.cos(angle), cy + orbit * math.sin(angle))
        ctx.stroke()

    def _draw_second_dot(self, ctx, cx, cy, angle, orbit, dot_radius):
        x = cx + orbit * math.cos(angle)
        y = cy + orbit * math.sin(angle)
        ctx.arc(x, y, dot_radius, 0, math.tau)
        ctx.set_source_rgb(*self._tertiary_rgb)
        ctx.fill()

    def _draw_curved_date(self, ctx, cx, cy, second_angle, second_orbit, dot_radius):
        text_str = datetime.datetime.now().strftime("%a %d")  # noqa: DTZ005
        base_text_angle = second_angle + math.pi

        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(self._font_desc)
        ctx.set_source_rgba(*self._on_primary_rgb, self.TEXT_ALPHA)

        text_radius = second_orbit + (
            dot_radius * 0.8 - self._dynamic_font_size_px // 2
        )

        char_angles = []
        total_angle_width = 0
        for char in text_str:
            layout.set_text(char, -1)
            char_width = layout.get_size()[0] / Pango.SCALE
            char_angle = (char_width / text_radius) * self.letter_spacing_factor
            char_angles.append(char_angle)
            total_angle_width += char_angle

        current_angle = base_text_angle - (total_angle_width / 2)

        for i, char in enumerate(text_str):
            layout.set_text(char, -1)
            current_angle += char_angles[i] / 2

            tx = cx + text_radius * math.cos(current_angle)
            ty = cy + text_radius * math.sin(current_angle)

            ctx.save()
            ctx.translate(tx, ty)
            ctx.rotate(current_angle + math.pi / 2)

            char_width, char_height = layout.get_size()
            ctx.move_to(
                -(char_width / Pango.SCALE) / 2, -(char_height / Pango.SCALE) / 2
            )
            PangoCairo.show_layout(ctx, layout)
            ctx.restore()

            current_angle += char_angles[i] / 2
