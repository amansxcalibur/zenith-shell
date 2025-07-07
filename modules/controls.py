from fabric.widgets.revealer import Revealer
from modules.volume import VolumeSlider, VolumeSmall
from modules.brightness import BrightnessSlider, BrightnessSmall, BrightnessMaterial3
from services.brightness_service import BrightnessService
import config.info as info

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib

class ControlsManager:
    _instance = None

    def __new__(cls, notch=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_controls(notch)
        return cls._instance

    def _init_controls(self, notch):
        self._init_volume_controls(notch)
        self._init_brightness_controls()

    def _init_volume_controls(self, notch):
        volume_slider = VolumeSlider(notch=notch)
        volume_overflow_slider = VolumeSlider(notch=notch)
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        transition = "slide-down" if not info.VERTICAL else "slide-right"

        self.volume_revealer = Revealer(
            transition_duration=250,
            transition_type=transition,
            child=volume_slider,
            child_revealed=False,
        )
        self.volume_overflow_revealer = Revealer(
            transition_duration=250,
            transition_type=transition,
            child=volume_overflow_slider,
            child_revealed=False,
        )

        self.vol_small = VolumeSmall(
            notch=notch,
            slider_instance=self.volume_revealer,
            overflow_instance=self.volume_overflow_revealer
        )

    def _init_brightness_controls(self):
        self.brightness_service = BrightnessService()
        self.brightness_service.connect("value-changed", self._handle_revealer)

        transition = "slide-down" if not info.VERTICAL else "slide-right"

        self.brightness_revealer = Revealer(
            name="brightness",
            transition_duration=250,
            transition_type=transition,
            child=BrightnessSlider(device="intel_backlight", service_instance=self.brightness_service),
            child_revealed=False,
        )

        self.brightness_slider_mui = BrightnessMaterial3(
            device="intel_backlight",
            service_instance=self.brightness_service
        )

        self.brightness_small = BrightnessSmall(
            device="intel_backlight",
            service_instance=self.brightness_service
        )

        self.hover_counter = 0
        self.hide_timer = None

    # getters
    def get_volume_revealer(self): return self.volume_revealer
    def get_volume_overflow_revealer(self): return self.volume_overflow_revealer
    def get_brightness_revealer(self): return self.brightness_revealer
    def get_volume_small(self): return self.vol_small
    def get_brightness_small(self): return self.brightness_small
    def get_brightness_slider_mui(self): return self.brightness_slider_mui

    def set_brightness(self):
        """Force brightness widgets to sync with system state."""
        self.brightness_small.init_brightness()
        self.brightness_slider_mui.init_brightness()

    # revealer
    def _handle_revealer(self, source, new_value, max_value):
        self._reveal()
        self._schedule_hide()

    def _reveal(self):
        self.hover_counter += 1
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        self.brightness_revealer.set_reveal_child(True)

    def _schedule_hide(self):
        if self.hover_counter > 0:
            self.hover_counter -= 1
        if self.hover_counter == 0:
            if self.hide_timer:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(1000, self._hide_revealer)

    def _hide_revealer(self):
        self.brightness_revealer.set_reveal_child(False)
        self.hide_timer = None
        return False
