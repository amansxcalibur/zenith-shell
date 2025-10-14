from typing import Tuple
import math
import cairo
import requests
from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.core.service import Service, Signal

import config.info as info
from utils.colors import get_css_variable, hex_to_rgb01

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, GLib, Pango, PangoCairo


class WeatherService(Service):
    _instance = None

    @Signal
    def value_changed(self, details: object) -> None:...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()
        self.CITY = "Kerala"
        self.API_URL = f"https://wttr.in/~{self.CITY}?format=%l+%z+%t+%f+%c+%C"
        self.details = {
            "location": "",
            "time": "",
            "temp": "__",
            "feels_like": "",
            "emoji": "",
            "description": "",
        }

        GLib.timeout_add_seconds(3600, self._fetch_weather)  # update every hour

    def _fetch_weather(self, *_):
        GLib.Thread.new("weather-fetch", self._fetch_weather_thread, None)
        return True

    def _fetch_weather_thread(self, *_):
        try:
            response = requests.get(url=self.API_URL, timeout=5)
            split_data = response.text.split()
            
            self.details = {
                "location": split_data[0].upper(),
                "time": f"Updated {split_data[1]}",
                "temp": split_data[2].lstrip("+").rstrip("C"),
                "feels_like": split_data[3].lstrip("+").rstrip("C"),
                "emoji": split_data[4],
                "description": " ".join(split_data[5:]),
            }
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            self.details["temp"] = "??"
            self.details["emoji"] = "_"
        
        self.value_changed(self.details)

class WeatherMini(Box):
    def __init__(self, **kwargs):
        super().__init__(name="weather-mini-container", spacing=3, **kwargs)

        self.details = {
            "location": "",
            "time": "",
            "temp": "__",
            "feels_like": "",
            "emoji": "_",
            "description": "",
        }

        self.temperature = Label(name="weather-temp", label=self.details['temp'])
        self.emoji = Label(name="weather-emoji", label=self.details['emoji'])

        self.children = [self.emoji, self.temperature]
        
        self.service = WeatherService()
        self.service.connect('value-changed', self.update_weather)
        self.service._fetch_weather()

    def update_weather(self, source, details:object):
        self.temperature.set_label(details['temp'])
        self.emoji.set_label(details['emoji'])

class WeatherPill(Gtk.DrawingArea):
    def __init__(self, size: Tuple[int, int] = (-1, 140), dark: bool = False):
        super().__init__()
        self.set_size_request(size[0], size[1])
        self.connect("draw", self.on_draw)

        self.dark = dark
        self.details = {
            "location": "",
            "time": "",
            "temp": "__",
            "feels_like": "",
            "emoji": "",
            "description": "",
        }

        self.service = WeatherService()
        self.service.connect('value-changed', self.update_weather)
        self.service._fetch_weather() # init
        
        self.show()

    def update_weather(self, source, details:object):
        self.details = details
        GLib.idle_add(self.queue_draw)

    def _get_color(self, css_var: str) -> Tuple[float, float, float]:
        """Get RGB color from CSS variable."""
        hex_color = get_css_variable(
            f"{info.HOME_DIR}/fabric/styles/colors.css", css_var
        )
        return hex_to_rgb01(hex_color)

    def _draw_circle(self, ctx: cairo.Context, cx: float, cy: float, radius: float):
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.close_path()
        ctx.fill_preserve()
        ctx.stroke()

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        base_radius = min(width, height) / 2.35

        circle_color = "--on-secondary" if self.dark else "--primary"
        ctx.set_source_rgb(*self._get_color(circle_color))
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

        # draw temperature text
        text_color = "--foreground" if self.dark else "--on-primary"
        ctx.set_source_rgb(*self._get_color(text_color))

        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(width/2.5)
        temp_text = self.details["temp"]
        extents = ctx.text_extents(temp_text)
        
        temp_cx = width - base_radius
        temp_cy = base_radius / 1.125
        ctx.move_to(
            temp_cx - (extents.x_bearing + extents.width / 2),
            temp_cy - (extents.y_bearing + extents.height / 2)
        )
        ctx.show_text(temp_text)

        # draw emoji
        text_color = "--foreground" if self.dark else "--foreground"
        ctx.set_source_rgb(*self._get_color(text_color))

        emoji_cx = base_radius / 1.35
        emoji_cy = width - base_radius / 1.35
        
        layout = PangoCairo.create_layout(ctx)
        layout.set_text(self.details["emoji"], -1)
        layout.set_font_description(Pango.FontDescription(f"Sans Bold {width/4}"))
        
        ink_rect, logical_rect = layout.get_pixel_extents()
        ctx.move_to(
            emoji_cx - logical_rect.width / 2,
            emoji_cy - logical_rect.height / 2
        )
        PangoCairo.show_layout(ctx, layout)