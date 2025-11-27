import math
import time
import cairo
import requests
from loguru import logger
from typing import Tuple
from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal, Property

from widgets.popup_window import SharedPopupWindow
import icons
from config.info import HOME_DIR
from utils.cursor import add_hover_cursor
from utils.colors import get_css_variable, hex_to_rgb01

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, GLib, Pango, PangoCairo


@dataclass
class WeatherData:
    location: str = ""
    time: str = ""
    temp: str = "__"
    feels_like: str = ""
    emoji: str = ""
    description: str = ""
    pressure: str = ""
    wind: str = ""
    humidity: str = ""

    @classmethod
    def from_api_response(cls, response_text: str) -> "WeatherData":
        """Parse API response into WeatherData"""
        try:
            split_data = response_text.split()
            return cls(
                location=split_data[0],
                time=f"Updated {split_data[1]}",
                temp=split_data[2].lstrip("+").rstrip("C"),
                feels_like=split_data[3].lstrip("+").rstrip("C"),
                emoji=split_data[4],
                pressure=split_data[5],
                wind=split_data[6],
                humidity=split_data[7],
                description=" ".join(split_data[8:]),
            )
        except (IndexError, AttributeError) as e:
            logger.error(f"Failed to parse weather data: {e}")
            return cls(temp="??", emoji="?")

    @classmethod
    def error_state(cls) -> "WeatherData":
        """Return weather data in error state"""
        return cls(temp="??", emoji="_")


class WeatherService(Service):
    _instance = None
    UPDATE_INTERVAL_SECONDS = 3600  # 1 hour
    API_TIMEOUT_SECONDS = 5

    @Signal
    def value_changed(self, weather_data: object) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        super().__init__()
        self._initialized = True

        self.CITY = "Kerala"
        self.API_URL = f"https://wttr.in/~{self.CITY}?format=%l+%z+%t+%f+%c+%P+%w+%h+%C"
        self._current_data = WeatherData()

        # update every hour
        GLib.timeout_add_seconds(self.UPDATE_INTERVAL_SECONDS, self._fetch_weather)
        self._fetch_weather()  # init

    @Property(str, "readable")
    def current_data(self):
        return self._current_data

    def _fetch_weather(self, *_):
        GLib.Thread.new("weather-fetch", self._fetch_weather_thread, None)
        return True

    def _fetch_weather_thread(self, *_):
        try:
            response = requests.get(url=self.API_URL, timeout=self.API_TIMEOUT_SECONDS)
            response.raise_for_status()
            weather_data = WeatherData.from_api_response(response.text)
            self._current_data = weather_data
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            weather_data = WeatherData.error_state()
            self._current_data = weather_data

        self.value_changed(weather_data)


class WeatherMini(EventBox):
    def __init__(self, **kwargs):
        super().__init__(name="weather-mini-container", spacing=3, **kwargs)

        self.service = WeatherService()
        initial_data = self.service.current_data

        self.temperature = Label(name="weather-temp", label=initial_data.temp)
        self.emoji = Label(name="weather-emoji", label=initial_data.emoji)

        self.children = Button(
            name="weather-refresh-btn",
            child=Box(children=[self.emoji, self.temperature]),
            on_clicked=self.service._fetch_weather,
        )

        add_hover_cursor(self)

        self.service.connect("value-changed", self._on_weather_update)

        self.build_popup_win()

    def build_popup_win(self):
        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(pointing_widget=self, child=WeatherCard())

    def _on_weather_update(self, source, data: WeatherData):
        self.temperature.set_label(data.temp)
        self.emoji.set_label(data.emoji)


class WeatherCard(Box):
    def __init__(self, **kwargs):
        super().__init__(spacing=5, orientation='v', **kwargs)

        self.service = WeatherService()
        initial_data = self.service.current_data

        self.last_updated_label = Label(name="weather-tile", style_classes=["updated-time-label"], label=f"Last updated: __", h_align="start")

        # temperature
        self.temperature_label = Label(
            name="weather-temp",
            style_classes=["card"],
            v_align="end",
            label=initial_data.temp,
        )

        self.emoji = Label(
            name="weather-emoji",
            style_classes=["card"],
            h_align="start",
            label=initial_data.emoji,
        )

        # location
        self.location = Label(
            name="weather-location",
            style_classes=["card"],
            h_align="end",
            label=initial_data.location,
        )

        # weather metrics
        self.humidity_label = Label(
            name="weather-humidity", style_classes=["card"], label=initial_data.humidity
        )

        self.pressure_label = Label(
            name="weather-pressure", style_classes=["card"], label=initial_data.pressure
        )

        self.wind_label = Label(
            name="weather-wind", style_classes=["card"], label=initial_data.wind
        )

        self.description = Label(
            name="weather-desc",
            style_classes=["card"],
            h_align="end",
            label=initial_data.description,
            line_wrap="word-char",
            max_chars_width=15,
        )

        self.children = [
            self.last_updated_label,
            Box(
                name="weather-tile",
                style_classes=["card"],
                spacing=20,
                children=[
                    Box(
                        orientation="v",
                        children=[
                            self.emoji,
                            Box(v_expand=True, children=self.temperature_label),
                        ],
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Box(
                                orientation="v",
                                v_align="start",
                                h_align="end",
                                children=[self.location, self.description],
                            ),
                            Box(
                                v_expand=True,
                                h_align="end",
                                v_align="end",
                                orientation="v",
                                children=[
                                    self._create_metric_row(
                                        self.humidity_label, icons.humidity
                                    ),
                                    self._create_metric_row(
                                        self.wind_label, icons.wind
                                    ),
                                    self._create_metric_row(
                                        self.pressure_label, icons.pressure
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]

        self.service.connect("value-changed", self.update_weather)

    def _create_metric_row(self, label: Label, icon_markup: str) -> Box:
        return Box(
            h_align="end",
            spacing=5,
            children=[
                label,
                Label(style_classes=["weather-icons"], markup=icon_markup),
            ],
        )

    def update_weather(self, source, data: WeatherData):
        self.temperature_label.set_label(data.temp)
        self.location.set_label(data.location)
        self.emoji.set_label(data.emoji)
        self.humidity_label.set_label(data.humidity)
        self.wind_label.set_label(data.wind)
        self.pressure_label.set_label(data.pressure)
        self.description.set_label(data.description)
        self.last_updated_label.set_label(f"Last updated: {time.strftime("%I:%M %p")}")


class WeatherPill(Gtk.DrawingArea):
    def __init__(self, size: Tuple[int, int] = (-1, 140), dark: bool = False):
        super().__init__()
        self.set_size_request(size[0], size[1])
        self.connect("draw", self.on_draw)

        self.dark = dark

        self.service = WeatherService()
        self._current_data = self.service.current_data
        self.service.connect("value-changed", self.on_weather_update)

        self.show()

    def on_weather_update(self, source, data: WeatherData):
        self._current_data = data
        GLib.idle_add(self.queue_draw)

    def _get_color(self, css_var: str) -> Tuple[float, float, float]:
        """Get RGB color from CSS variable."""
        hex_color = get_css_variable(
            f"{HOME_DIR}/fabric/styles/colors.css", css_var
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
        ctx.set_font_size(width / 2.5)

        temp_text = self._current_data.temp
        extents = ctx.text_extents(temp_text)

        temp_cx = width - base_radius
        temp_cy = base_radius / 1.125
        ctx.move_to(
            temp_cx - (extents.x_bearing + extents.width / 2),
            temp_cy - (extents.y_bearing + extents.height / 2),
        )
        ctx.show_text(temp_text)

        # draw emoji
        text_color = "--foreground" if self.dark else "--foreground"
        ctx.set_source_rgb(*self._get_color(text_color))

        emoji_cx = base_radius / 1.35
        emoji_cy = width - base_radius / 1.35

        layout = PangoCairo.create_layout(ctx)
        layout.set_text(self._current_data.emoji, -1)
        layout.set_font_description(Pango.FontDescription(f"Sans Bold {width/4}"))

        ink_rect, logical_rect = layout.get_pixel_extents()
        ctx.move_to(
            emoji_cx - logical_rect.width / 2, emoji_cy - logical_rect.height / 2
        )
        PangoCairo.show_layout(ctx, layout)
