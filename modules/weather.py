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
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from config.info import ROOT_DIR
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
    def from_open_meteo(cls, weather_json: dict, location_json: dict) -> "WeatherData":
        try:
            current = weather_json["current"]
            wmo_code = current["weather_code"]

            emoji, desc = cls._get_wmo_info(wmo_code)

            return cls(
                location=f"{location_json.get('city', 'Unknown')}, {location_json.get('country_code', '')}",
                time=f"Updated {current['time'].split('T')[-1]}",
                temp=f"{round(current['temperature_2m'])}",
                feels_like=f"{round(current['apparent_temperature'])}",
                emoji=emoji,
                description=desc,
                pressure=f"{current['surface_pressure']}hPa",
                wind=f"{current['wind_speed_10m']}km/h",
                humidity=f"{current['relative_humidity_2m']}%",
            )
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse weather data: {e}")
            return cls.error_state()

    @staticmethod
    def _get_wmo_info(code: int) -> tuple:
        mapping = {
            0: ("☀️", "Clear sky"),
            1: ("🌤️", "Mostly clear"),
            2: ("⛅", "Partly cloudy"),
            3: ("☁️", "Overcast"),
            45: ("🌫️", "Fog"),
            48: ("🌫️", "Icy fog"),
            51: ("🌦️", "Light drizzle"),
            53: ("🌦️", "Moderate drizzle"),
            55: ("🌦️", "Heavy drizzle"),
            56: {"🌦️", "Light freezing drizzle"},  #
            57: {"🌦️", "Freezing drizzle"},  #
            61: ("🌧️", "Slight rain"),
            63: ("🌧️", "Moderate rain"),
            65: ("🌧️", "Heavy rain"),
            66: {"🌦️", "Light freezing rain"},  #
            67: {"🌦️", "Freezing rain"},  #
            71: ("❄️", "Slight snow"),
            73: ("❄️", "Moderate snow"),
            75: ("❄️", "Heavy snow"),
            77: ("❄️", "Snow grains"),
            80: ("🌦️", "Slight rain showers"),
            81: ("🌧️", "Moderate rain showers"),
            82: ("⛈️", "Violent rain showers"),
            85: {"🌨️", "Light snow showers"},
            86: {"🌨️", "Snow showers"},
            95: ("🌩️", "Thunderstorm"),
            96: ("🌩️", "Thunderstorm + Light hail"),
            99: ("🌩️", "Thunderstorm + Hail"),
        }
        return mapping.get(code, ("❓", "Unknown"))

    @classmethod
    def error_state(cls) -> "WeatherData":
        """Return weather data in error state"""
        return cls(temp="??", emoji="?")


class WeatherService(Service):
    _instance = None
    UPDATE_INTERVAL_SECONDS = 3600  # 1 hour
    API_TIMEOUT_SECONDS = 10

    @Signal
    def value_changed(self, weather_data: object) -> None: ...

    @Property(object, "readable")
    def current_data(self):
        return self._current_data

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
        self._current_data = WeatherData()

        # update every hour
        GLib.timeout_add_seconds(self.UPDATE_INTERVAL_SECONDS, self._fetch_weather)
        self._fetch_weather()  # init

    def _fetch_weather(self, *_):
        GLib.Thread.new("weather-fetch", self._fetch_weather_thread, None)
        return True

    def _fetch_weather_thread(self, *_):
        try:
            ip_resp = requests.get(
                "https://ipapi.co/json/",
                timeout=self.API_TIMEOUT_SECONDS,
                headers={"User-agent": "your bot 0.1"},
            )
            ip_resp.raise_for_status()

            loc = ip_resp.json()
            lat, lon = loc.get("latitude"), loc.get("longitude")

            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&"
                f"current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,surface_pressure,wind_speed_10m"
            )
            weather_resp = requests.get(weather_url, timeout=self.API_TIMEOUT_SECONDS)
            weather_resp.raise_for_status()

            weather_data = WeatherData.from_open_meteo(weather_resp.json(), loc)
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

        self.temperature = MaterialFontLabel(
            name="weather-temp",
            text=initial_data.temp,
            font_family="Google Sans Flex",
            wght=500,
        )
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
        super().__init__(spacing=5, orientation="v", **kwargs)

        self.service = WeatherService()
        initial_data = self.service.current_data

        self.last_updated_label = Label(
            name="weather-tile",
            style_classes=["updated-time-label"],
            label="Last updated: __",
            h_align="start",
        )

        # temperature
        self.temperature_label = MaterialFontLabel(
            name="weather-temp",
            style_classes=["card"],
            v_align="end",
            text=initial_data.temp,
            font_family="Google Sans Flex",
            wght=500,
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
                                        self.humidity_label, icons.humidity.symbol()
                                    ),
                                    self._create_metric_row(
                                        self.wind_label, icons.wind.symbol()
                                    ),
                                    self._create_metric_row(
                                        self.pressure_label, icons.pressure.symbol()
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]

        self.service.connect("value-changed", self.update_weather)

    def _create_metric_row(self, label: Label, icon_symbol: str) -> Box:
        return Box(
            h_align="end",
            spacing=5,
            children=[
                label,
                MaterialIconLabel(
                    style_classes=["weather-icons"], icon_text=icon_symbol
                ),
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
        self.last_updated_label.set_label(f"Last updated: {time.strftime('%I:%M %p')}")


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
        hex_color = get_css_variable(f"{ROOT_DIR}/styles/colors.css", css_var)
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

        # draw temperature text
        text_color = "--foreground" if self.dark else "--on-primary"
        ctx.set_source_rgb(*self._get_color(text_color))

        layout = PangoCairo.create_layout(ctx)
        layout.set_text(str(self._current_data.temp), -1)

        font_desc = Pango.FontDescription("Google Sans Flex Bold")
        font_desc.set_size(int(width / 3 * Pango.SCALE))
        font_desc.set_variations("ROND=100")
        layout.set_font_description(font_desc)

        ink_rect, logical_rect = layout.get_pixel_extents()
        temp_cx = width - base_radius
        temp_cy = base_radius / 1.125
        ctx.move_to(
            temp_cx - (logical_rect.width / 2), temp_cy - (logical_rect.height / 2)
        )
        PangoCairo.show_layout(ctx, layout)

        # draw emoji
        text_color = "--foreground" if self.dark else "--foreground"
        ctx.set_source_rgb(*self._get_color(text_color))

        emoji_cx = base_radius / 1.35
        emoji_cy = width - base_radius / 1.35

        layout = PangoCairo.create_layout(ctx)
        layout.set_text(self._current_data.emoji, -1)
        layout.set_font_description(Pango.FontDescription(f"Sans Bold {width / 4}"))

        ink_rect, logical_rect = layout.get_pixel_extents()
        ctx.move_to(
            emoji_cx - logical_rect.width / 2, emoji_cy - logical_rect.height / 2
        )
        PangoCairo.show_layout(ctx, layout)
