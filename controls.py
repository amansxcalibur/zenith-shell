from volume import VolumeSlider, VolumeSmall
from brightness import BrightnessSlider, BrightnessSmall
from fabric.widgets.revealer import Revealer
import info

class ControlsManager:
    _instance = None

    def __new__(cls, notch=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_controls(notch)
        return cls._instance

    def _init_controls(self, notch):
        volume_slider = VolumeSlider(notch = self)
        volume_overflow_slider = VolumeSlider(notch = self)
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        self.volume_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_slider,
                    child_revealed=False,
                )
        
        self.volume_overflow_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_overflow_slider,
                    child_revealed=False,
                )
        
        self.vol_small = VolumeSmall(notch = self, slider_instance=self.volume_revealer, overflow_instance = self.volume_overflow_revealer)

        self.brightness_revealer = Revealer(
            name="brightness",
            transition_duration=250,
            transition_type="slide-down" if not info.VERTICAL else "slide-right",
            child=BrightnessSlider(),
            child_revealed=True
        )
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
