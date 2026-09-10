import math
import time
import cairo
import requests
from loguru import logger
from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal, Property

from widgets.overrides import Svg
from widgets.popup_window import SharedPopupWindow
from widgets.loader import MaterialExpressiveLoader
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from svg import underscore, question_mark
from svg.weather import dark as weather_dark
from svg.weather import light as weather_light
from config.info import ROOT_DIR
from utils.cursor import add_hover_cursor
from utils.colors import get_css_variable, hex_to_rgb01

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, GLib, Pango, PangoCairo, Rsvg  # type: ignore


@dataclass
class WeatherData:
    location: str = ""
    time: str = ""
    temp: str = "__"
    feels_like: str = ""
    emoji_name: str = "underscore"
    description: str = ""
    pressure: str = ""
    wind: str = ""
    humidity: str = ""

    @classmethod
    def from_open_meteo(cls, weather_json: dict, location_json: dict) -> "WeatherData":
        try:
            current = weather_json["current"]
            wmo_code = current["weather_code"]

            emoji_name, desc = cls._get_wmo_info(wmo_code)

            return cls(
                location=f"{location_json.get('city', 'Unknown')}",
                time=f"Updated {current['time'].split('T')[-1]}",
                temp=f"{round(current['temperature_2m'])}°",
                feels_like=f"{round(current['apparent_temperature'])}",
                emoji_name=emoji_name,
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
            0: ("sunny", "Clear sky"),
            1: ("mostly_sunny", "Mostly clear"),
            2: ("partly_cloudy", "Partly cloudy"),
            3: ("cloudy", "Overcast"),
            45: ("fog", "Fog"),
            48: ("fog", "Icy fog"),
            # rain
            51: ("drizzle", "Light drizzle"),
            53: ("drizzle", "Moderate drizzle"),
            55: ("drizzle", "Heavy drizzle"),
            56: ("sleet_hail", "Light freezing drizzle"),
            57: ("sleet_hail", "Freezing drizzle"),
            61: ("drizzle", "Slight rain"),
            63: ("heavy_rain", "Moderate rain"),
            65: ("heavy_rain", "Heavy rain"),
            66: ("wintry_mix", "Light freezing rain"),
            67: ("wintry_mix", "Freezing rain"),
            80: ("drizzle", "Slight rain showers"),
            81: ("heavy_rain", "Moderate rain showers"),
            82: ("heavy_rain", "Violent rain showers"),
            # snow
            71: ("flurries", "Slight snow"),
            73: ("snow_showers", "Moderate snow"),
            75: ("heavy_snow", "Heavy snow"),
            77: ("icy", "Snow grains"),
            85: ("blowing_snow", "Light snow showers"),
            86: ("blizzard", "Snow showers"),
            95: ("thunderstorms", "Thunderstorm"),
            96: ("strong_thunderstorms", "Thunderstorm + Light hail"),
            99: ("strong_thunderstorms", "Thunderstorm + Hail"),
        }
        return mapping.get(code, ("question_mark", "Unknown"))

    def get_emoji(self, dark: bool = False):
        if self.emoji_name == "question_mark":
            return question_mark
        if self.emoji_name == "underscore":
            return underscore

        icon_module = weather_dark if dark else weather_light
        return getattr(icon_module, self.emoji_name, question_mark)

    @classmethod
    def error_state(cls) -> "WeatherData":
        """Return weather data in error state"""
        return cls(temp="??", emoji_name=question_mark)


class WeatherService(Service):
    _instance = None
    UPDATE_INTERVAL_SECONDS = 600  # 10 mins
    API_TIMEOUT_SECONDS = 10

    @Signal
    def value_changed(self, weather_data: object) -> None: ...

    @Signal
    def is_loading(self, loading: bool) -> None: ...

    @Property(object, "readable")
    def current_data(self) -> WeatherData:
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
        self._is_fetching = False

        # update every hour
        GLib.timeout_add_seconds(self.UPDATE_INTERVAL_SECONDS, self._fetch_weather)
        self._fetch_weather()  # init

    def _fetch_weather(self, *_):
        if self._is_fetching:
            return

        self._is_fetching = True
        self.is_loading(True)

        GLib.Thread.new("weather-fetch", self._fetch_weather_thread, None)
        return True

    def _fetch_weather_thread(self, *_):
        try:
            ip_url = "http://ip-api.com/json/"
            ip_resp = requests.get(ip_url, timeout=self.API_TIMEOUT_SECONDS)
            ip_resp.raise_for_status()

            loc = ip_resp.json()
            lat = loc.get("lat")
            lon = loc.get("lon")

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

        GLib.idle_add(self._on_fetch_complete, weather_data)

    def _on_fetch_complete(self, weather_data: WeatherData):
        self._current_data = weather_data
        self._is_fetching = False
        self.value_changed(weather_data)
        self.is_loading(False)
        return False


class WeatherMini(EventBox):
    def __init__(self, dark: bool = True, **kwargs):
        super().__init__(name="weather-mini-container", spacing=3, **kwargs)
        self.dark = dark

        self.service = WeatherService()
        initial_data: WeatherData = self.service.current_data

        self.temperature = MaterialFontLabel(
            name="weather-temp",
            text=initial_data.temp,
            font_family="Google Sans Flex",
            wght=500,
        )

        self.emoji_svg = Svg(
            name="weather-emoji",
            size=(20, 20),
            svg_string=initial_data.get_emoji(self.dark),
        )

        self.refresh_btn = Button(
            name="weather-mini",
            child=MaterialIconLabel(
                name="weather-refresh-label", icon_text=icons.refresh.symbol()
            ),
            on_clicked=self.service._fetch_weather,
        )
        self.weather_box = Box(
            name="weather-mini", spacing=2, children=[self.emoji_svg, self.temperature]
        )

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            children=[self.weather_box, self.refresh_btn],
        )

        self.children = Box(children=self.stack)

        self.connect("enter-notify-event", self._on_hover, True)
        self.connect("leave-notify-event", self._on_hover, False)
        self.service.connect("value-changed", self._on_weather_update)

        self.build_popup_win()

        add_hover_cursor(self)

    def _on_hover(self, _source, event, reveal: bool):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.stack.set_visible_child(
                self.refresh_btn if reveal else self.weather_box
            )

    def build_popup_win(self):
        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(pointing_widget=self, child=WeatherCard())

    def _on_weather_update(self, source, data: WeatherData):
        self.temperature.set_label(data.temp)
        self.emoji_svg.set_from_string(data.get_emoji(self.dark))


class WeatherCard(Box):
    def __init__(self, dark: bool = True, **kwargs):
        super().__init__(spacing=5, orientation="v", **kwargs)
        self.dark = dark

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

        self.emoji_svg = Svg(
            name="weather-emoji",
            style_classes=["card"],
            h_align="start",
            v_align="start",
            h_expand=True,
            v_expand=True,
            size=(50, 50),
            svg_string=initial_data.get_emoji(self.dark),
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

        self.main_tile = Box(
            name="weather-tile",
            style_classes=["card"],
            spacing=20,
            children=[
                Box(
                    orientation="v",
                    children=[
                        self.emoji_svg,
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
        )

        self.loader = MaterialExpressiveLoader(name="weather-loader", size=100)
        self.loader.set_visible(False)
        self.loader_container = Box(
            name="weather-loader-overlay",
            style_classes="active",
            h_expand=True,
            v_expand=True,
            children=self.loader,
            all_visible=True,
        )

        self.overlay = Overlay(
            h_expand=True,
            v_expand=True,
            child=self.main_tile,
            overlays=[self.loader_container],
        )

        self.children = [
            self.last_updated_label,
            self.overlay,
        ]

        self.service.connect("value-changed", self.update_weather)
        self.service.connect("is-loading", lambda _, loading: self.set_loading(loading))

    def set_loading(self, is_loading: bool):
        if is_loading:
            self.loader.reset()
            self.loader.set_visible(True)
            self.loader_container.add_style_class("active")
        else:
            self.loader.set_visible(False)
            self.loader_container.remove_style_class("active")

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

    def update_weather(self, source, data):
        self.temperature_label.set_label(data.temp)
        self.location.set_label(data.location)
        self.emoji_svg.set_from_string(data.get_emoji(self.dark))
        self.humidity_label.set_label(data.humidity)
        self.wind_label.set_label(data.wind)
        self.pressure_label.set_label(data.pressure)
        self.description.set_label(data.description)
        self.last_updated_label.set_label(f"Last updated: {time.strftime('%I:%M %p')}")

        self.set_loading(False)


class WeatherPill(Gtk.DrawingArea):
    def __init__(self, size: tuple[int, int] = (-1, 160), dark: bool = False):
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
        svg_string = data.get_emoji(self.dark)
        try:
            self._svg_handle = Rsvg.Handle.new_from_data(svg_string.encode())
        except Exception as e:
            logger.error(f"Failed to load SVG: {e}")
            self._svg_handle = None
        GLib.idle_add(self.queue_draw)

    def _get_rgb_color(self, css_var: str) -> tuple[float, float, float]:
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
        ctx.set_source_rgb(*self._get_rgb_color(circle_color))
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
        ctx.set_source_rgb(*self._get_rgb_color(text_color))

        layout = PangoCairo.create_layout(ctx)
        layout.set_text(str(self._current_data.temp), -1)

        font_desc = Pango.FontDescription("Google Sans Flex Bold")
        font_desc.set_size(int(width / 3 * Pango.SCALE))
        font_desc.set_variations("ROND=100")
        layout.set_font_description(font_desc)

        _, logical_rect = layout.get_pixel_extents()
        temp_cx = width - base_radius
        temp_cy = base_radius / 1.125
        ctx.move_to(
            temp_cx - (logical_rect.width / 2), temp_cy - (logical_rect.height / 2)
        )
        PangoCairo.show_layout(ctx, layout)

        # draw emoji
        if hasattr(self, "_svg_handle") and self._svg_handle:
            target_size = width / 3

            dims = self._svg_handle.get_dimensions()
            svg_w, svg_h = dims.width, dims.height

            scale_x = target_size / svg_w if svg_w > 0 else 1
            scale_y = target_size / svg_h if svg_h > 0 else 1

            emoji_cx = base_radius / 1.35
            emoji_cy = width - base_radius / 1.35

            ctx.save()
            ctx.translate(emoji_cx - (target_size / 2), emoji_cy - (target_size / 2))
            ctx.scale(scale_x, scale_y)

            self._svg_handle.render_cairo(ctx)
            ctx.restore()
