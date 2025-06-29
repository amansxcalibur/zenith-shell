from fabric.widgets.revealer import Revealer

from modules.volume import VolumeSlider, VolumeSmall
from modules.brightness import BrightnessSlider, BrightnessSmall, BrightnessMaterial3
import config.info as info

class ControlsManager:
    _instance = None

    def __new__(cls, notch=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_controls(notch)
        return cls._instance

    def _init_controls(self, notch):
        volume_slider = VolumeSlider(notch = notch)
        volume_overflow_slider = VolumeSlider(notch = notch)
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        # 0-100
        self.volume_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_slider,
                    child_revealed=False,
                )
        
        # 100-200+
        self.volume_overflow_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_overflow_slider,
                    child_revealed=False,
                )
        
        self.vol_small = VolumeSmall(notch = notch, slider_instance=self.volume_revealer, overflow_instance = self.volume_overflow_revealer)

        self.brightness_revealer = Revealer(
            name="brightness",
            transition_duration=250,
            transition_type="slide-down" if not info.VERTICAL else "slide-right",
            child=BrightnessSlider(),
            child_revealed=True
        )
        self.brightness_slider_mui = BrightnessMaterial3(device="intel_backlight")
        self.brightness_small = BrightnessSmall(device="intel_backlight", slider_instance=self.brightness_revealer)

    def get_volume_revealer(self):
        return self.volume_revealer
    
    def get_volume_overflow_revealer(self):
        return self.volume_overflow_revealer

    def get_brightness_revealer(self):
        return self.brightness_revealer
    
    def get_volume_small(self):
        return self.vol_small
    
    def get_brightness_small(self):
        return self.brightness_small
    
    def get_brightness_slider_mui(self):
        return self.brightness_slider_mui
    
    def set_brightness(self):
        self.brightness_small.update_brightness()
        self.brightness_slider_mui.update_brightness()
