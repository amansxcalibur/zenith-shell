from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.eventbox import EventBox

from modules.volume import VolumeSmall, VolumeSlider, VolumeMaterial3
from modules.brightness import BrightnessSlider, BrightnessSmall, BrightnessMaterial3
from widgets.popup_window import PopupWindow
from services.brightness_service import BrightnessService
from services.volume_service import VolumeService
import config.info as info

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib


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

    def __new__(cls, notch=None):
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
        self.vol_brightness_box = EventBox(child=Box(
            name="vol-brightness-container",
            orientation="h",
            children=[self.volume_manager.vol_small, self.brightness_manager.brightness_small],
        ))
        self.popup_win = PopupWindow(
            widget=self.vol_brightness_box,
            child=Box(
                name="control-slider-mui-container",
                spacing=7,
                children=[self.popup_slider_vol, self.popup_slider_brightness],
            ),
        )

    # getters
    def get_controls_box(self): return self.vol_brightness_box
    def get_volume_small(self): return self.volume_manager.vol_small
    def get_volume_revealer(self): return self.volume_manager.volume_revealer.revealer
    def get_volume_overflow_revealer(self): return self.volume_manager.volume_overflow_revealer.revealer
    def get_brightness_small(self): return self.brightness_manager.brightness_small
    def get_brightness_slider_mui(self): return self.brightness_manager.brightness_slider_mui
    def get_brightness_revealer(self): return self.brightness_manager.brightness_revealer.revealer


class BrightnessManager:
    _instance = None

    def __new__(cls, notch=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.service = BrightnessService()
        self._init_widgets()
        self._connect_signals()

    def _init_widgets(self):
        transition = "slide-down" if not info.VERTICAL else "slide-right"

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

    def __new__(cls, notch=None):
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
        volume_overflow_slider = VolumeSlider(min_value=1, max_value=2)
        self.mui_slider = VolumeMaterial3(min_value=0, max_value=2, orientation="v")
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        transition = "slide-down" if not info.VERTICAL else "slide-right"

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

        self.volume_revealer_set = [self.volume_revealer, self.volume_overflow_revealer]

        self.vol_small = VolumeSmall()

    def _connect_signals(self):
        self.service.connect("value-changed", self._on_volume_changed)

    def _on_volume_changed(self, source, new_val, max_val, is_mute):
        if new_val > max_val:
            self.volume_revealer._hide()
            self.volume_overflow_revealer.reveal()
        else:
            self.volume_overflow_revealer._hide()
            self.volume_revealer.reveal()
