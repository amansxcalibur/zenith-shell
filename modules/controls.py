from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.eventbox import EventBox

import icons
from modules.audio_panel import AudioPanel
from widgets.track_decor import TrackDecor

from modules.volume import (
    FULL_VOLUME,
    VolumeSmall,
    VolumeSlider,
    VolumeMaterial3,
    MicSmall,
    MicSlider,
    MicMaterial3,
)
from modules.brightness import (
    BACKLIGHT_SUPPORTED,
    BrightnessSlider,
    BrightnessSmall,
    BrightnessMaterial3,
)
from widgets.popup_window import SharedPopupWindow
from services.volume_service import (
    MAX_MIC_VOLUME,
    MAX_VOLUME,
    MAX_VOLUME_REASON,
    VolumeService,
)
from services.brightness_service import BrightnessService
from config.config import config

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # type: ignore


class AutoHideRevealer:
    def __init__(self, revealer, timeout=1000):
        self.revealer = revealer
        self.timeout = timeout
        self.hover_counter = 0
        self.hide_timer = None

    def reveal(self):
        self.hover_counter += 1
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        self.revealer.set_reveal_child(True)
        self._schedule_hide()

    def _schedule_hide(self):
        if self.hover_counter > 0:
            self.hover_counter -= 1
        if self.hover_counter == 0:
            if self.hide_timer:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(self.timeout, self._hide)

    def _hide(self):
        self.revealer.set_reveal_child(False)
        self.hide_timer = None
        return False


class ControlsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_controls()
        return cls._instance

    def _init_controls(self):
        self.volume_manager = VolumeManager()
        self.brightness_manager = BrightnessManager()
        self._init_controls_box()

    def _init_controls_box(self):
        self.popup_slider_vol = self.volume_manager.mui_slider
        self.popup_slider_brightness = BrightnessMaterial3(
            device="intel_backlight",
            service_instance=self.brightness_manager.service,
            orientation="v",
        )
        self.popup_slider_mic = self.volume_manager.mui_mic_slider
        self.vol_brightness_container = Box(
            name="vol-brightness-container",
            orientation="h",
            children=[
                self.volume_manager.mic_small,
                self.volume_manager.vol_small,
                self.brightness_manager.brightness_small,
            ],
        )
        self.vol_brightness_box = EventBox(child=self.vol_brightness_container)

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(
            pointing_widget=self.vol_brightness_box,
            child=self._build_popup(),
        )

    def _build_popup(self) -> Box:
        volume_service = self.volume_manager.service

        def volume_icon():
            volume, muted = volume_service.get_current_volume()
            if muted or volume <= 0:
                return icons.material.volume_off
            return (
                icons.material.volume_down if volume < 0.5 else icons.material.volume_up
            )

        def brightness_icon():
            value = self.popup_slider_brightness.get_value()
            if value < 1 / 3:
                return icons.material.brightness_low
            if value < 2 / 3:
                return icons.material.brightness_medium
            return icons.material.brightness_high

        mic_decor = TrackDecor(
            self.popup_slider_mic,
            icon=lambda: (
                icons.material.mic_off
                if volume_service.get_mic_status()[1]
                else icons.material.mic
            ),
        )
        volume_decor = TrackDecor(
            self.popup_slider_vol, icon=volume_icon, stops=[FULL_VOLUME]
        )
        TrackDecor(self.popup_slider_brightness, icon=brightness_icon)

        # muting changes no value, so nothing else repaints the icon
        volume_service.connect(
            "speaker-volume-changed", lambda *_: volume_decor.refresh()
        )
        volume_service.connect("mic-volume-changed", lambda *_: mic_decor.refresh())

        def set_shown(widget, shown):
            widget.set_no_show_all(not shown)
            widget.set_visible(shown)

        volume_service.connect(
            "mic-available-changed",
            lambda _s, ok: set_shown(self.popup_slider_mic, ok),
        )
        set_shown(self.popup_slider_mic, volume_service.is_mic_available())
        set_shown(self.popup_slider_brightness, BACKLIGHT_SUPPORTED)

        return Box(
            name="control-slider-mui-container",
            spacing=8,
            children=[
                Box(
                    name="control-sliders",
                    spacing=7,
                    # a device list opening grows the panel; not the sliders
                    v_align="start",
                    homogeneous=True,
                    children=[
                        self.popup_slider_mic,
                        self.popup_slider_vol,
                        self.popup_slider_brightness,
                    ],
                ),
                Box(name="control-divider"),
                AudioPanel(volume_service),
            ],
        )

    # getters
    def get_controls_box(self, vertical: bool = False):
        self.vol_brightness_container.set_orientation(
            Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL
        )
        return self.vol_brightness_box

    def get_volume_small(self):
        return self.volume_manager.vol_small

    def get_volume_revealer(self):
        return self.volume_manager.volume_revealer.revealer

    def get_volume_overflow_revealer(self):
        return self.volume_manager.volume_overflow_revealer.revealer

    def get_mic_revealer(self):
        return self.volume_manager.mic_revealer.revealer

    def get_brightness_small(self):
        return self.brightness_manager.brightness_small

    def get_brightness_slider_mui(self):
        return self.brightness_manager.brightness_slider_mui

    def get_brightness_revealer(self):
        return self.brightness_manager.brightness_revealer.revealer


class BrightnessManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.service = BrightnessService()
        self._init_widgets()
        self._connect_signals()

    def _init_widgets(self):
        transition = "slide-down" if not config.VERTICAL else "slide-right"

        self.brightness_revealer = AutoHideRevealer(
            revealer=Revealer(
                name="brightness",
                transition_duration=250,
                transition_type=transition,
                child=BrightnessSlider(
                    device="intel_backlight", service_instance=self.service
                ),
                child_revealed=False,
            )
        )

        self.brightness_slider_mui = BrightnessMaterial3(
            device="intel_backlight", service_instance=self.service
        )

        self.brightness_small = BrightnessSmall(
            device="intel_backlight", service_instance=self.service
        )

        self.brightness_revealer_set = [self.brightness_revealer]

    def _connect_signals(self):
        self.service.connect("value-changed", self._on_brightness_changed)

    def _on_brightness_changed(self, source, new_val, max_val):
        self.brightness_revealer.reveal()

    def set_brightness(self):
        self.brightness_small.init_brightness()
        self.brightness_slider_mui.init_brightness()


class VolumeManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.service = VolumeService()
        self._init_widgets()
        self._connect_signals()

    def _init_widgets(self):
        volume_slider = VolumeSlider(min_value=0, max_value=1)
        volume_overflow_slider = VolumeSlider(min_value=1, max_value=MAX_VOLUME)
        self.mui_slider = VolumeMaterial3(
            min_value=0, max_value=MAX_VOLUME, orientation="v"
        )
        # says why it stops there, once it does
        self.mui_slider.connect(
            "value-changed",
            lambda s: s.set_tooltip_text(
                MAX_VOLUME_REASON if s.get_value() >= MAX_VOLUME - 0.005 else None
            ),
        )
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        mic_slider = MicSlider(min_value=0, max_value=MAX_MIC_VOLUME)
        self.mui_mic_slider = MicMaterial3(
            min_value=0, max_value=MAX_MIC_VOLUME, orientation="v"
        )

        transition = "slide-down" if not config.VERTICAL else "slide-right"

        self.volume_revealer = AutoHideRevealer(
            revealer=Revealer(
                transition_duration=250,
                transition_type=transition,
                child=volume_slider,
                child_revealed=False,
            )
        )
        self.volume_overflow_revealer = AutoHideRevealer(
            revealer=Revealer(
                transition_duration=250,
                transition_type=transition,
                child=volume_overflow_slider,
                child_revealed=False,
            )
        )

        self.mic_revealer = AutoHideRevealer(
            revealer=Revealer(
                transition_duration=250,
                transition_type=transition,
                child=mic_slider,
                child_revealed=False,
            )
        )

        self.volume_mic_revealer_set = [
            self.volume_revealer,
            self.volume_overflow_revealer,
            mic_slider,
        ]

        self.vol_small = VolumeSmall()
        self.mic_small = MicSmall()

    def _connect_signals(self):
        self.service.connect("speaker-volume-changed", self._on_volume_changed)
        self.service.connect("mic-volume-changed", self._on_mic_volume_changed)

    def _on_volume_changed(self, source, new_val, max_val, is_mute):
        if new_val > max_val:
            self.volume_revealer._hide()
            self.volume_overflow_revealer.reveal()
        else:
            self.volume_overflow_revealer._hide()
            self.volume_revealer.reveal()

    def _on_mic_volume_changed(self, *_):
        self.mic_revealer.reveal()
