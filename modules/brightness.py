from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox

from config.config import config
from widgets.material_label import MaterialIconLabel
from widgets.animated_scale import AnimatedScale, AnimatedCircularScale

import icons
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk  # noqa: E402


def supports_backlight():
    try:
        output = (
            subprocess.check_output(["brightnessctl", "-l"]).decode("utf-8").lower()
        )
        return "backlight" in output
    except Exception:
        return False


BACKLIGHT_SUPPORTED = supports_backlight()


class BrightnessSlider(AnimatedScale):
    def __init__(self, device: str, service_instance, **kwargs):
        super().__init__(
            name="control-slider",
            orientation="h" if not config.VERTICAL else "v",
            h_expand=True,
            has_origin=True,
            inverted=True if config.VERTICAL else False,
            style_classes="" if not config.VERTICAL else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.service_instance = service_instance
        self.device = device
        self.current = 0
        self.max = 0
        self.percentage = 0
        self.exist = BACKLIGHT_SUPPORTED
        self.hide_timer = None
        self.hover_counter = 0
        self.add_style_class("brightness")
        self.update_from_user = False
        self.ui_updating = False
        self.init_brightness()
        self.service_instance.connect("value-changed", self.update_brightness_slider)
        self.connect("change-value", self.set_brightness)

    def init_brightness(self):
        if self.exist:
            self.current = self.service_instance.get_brightness()
            self.max = self.service_instance.get_max_brightness()
            self.percentage = self.current / self.max
            self.update_brightness_slider(None, self.current, self.max)

    def update_brightness_slider(self, source, new_value, max_value):
        if max_value <= 0 or self.ui_updating:
            return

        self.ui_updating = True
        brightness = new_value / max_value
        if self.update_from_user:
            self.set_value(brightness)
        else:
            self.animate_value(brightness)
        self.update_from_user = False
        self.ui_updating = False

    def set_brightness(self, source, scroll_type, value):
        self.update_from_user = True
        new_value = int(value * 100)
        self.service_instance.set_brightness(new_value)


class BrightnessSmall(Box):
    def __init__(self, device: str, service_instance, **kwargs):
        super().__init__(name="button-bar-brightness", **kwargs)
        # self.brightness = Brightness.get_initial()
        # if self.brightness.screen_brightness == -1:
        #     self.destroy()
        #     return
        self.service_instance = service_instance
        self.device = device
        self.current = 0
        self.max = 0
        self.percentage = 0
        self.exist = BACKLIGHT_SUPPORTED

        self.brightness_label = MaterialIconLabel(
            name="brightness-label",
            FILL=0,
            wght=600,
            icon_text=icons.brightness.symbol(),
        )
        self.progress_bar = AnimatedCircularScale(
            name="button-brightness",
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
            child=self.brightness_label,
        )
        self.brightness_button = Button(name="brightness-button")
        self.event_box = EventBox(
            # events=["scroll", "smooth-scroll"],
            events="scroll",
            v_expand=True,
            h_expand=True,
            child=Overlay(child=self.progress_bar, overlays=self.brightness_button),
        )
        self.event_box.connect("scroll-event", self.on_scroll)

        self.add(self.event_box)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)

        self.service_instance.connect("value-changed", self.on_brightness_changed)
        self.init_brightness()

    def init_brightness(self):
        if self.exist:
            self.current = self.service_instance.get_brightness()
            self.max = self.service_instance.get_max_brightness()
            self.percentage = self.current / self.max
            self.on_brightness_changed(self, self.current, self.max)

    def on_scroll(self, widget, event):
        match event.direction:
            case 0:
                self.service_instance.decrement_brightness()
            case 1:
                self.service_instance.increment_brightness()

    def on_brightness_changed(self, source, new_value, max_value):
        self.percentage = 100 * new_value / max_value
        self.progress_bar.animate_value(self.percentage / 100)

    # def destroy(self):
    #     if self._update_source_id is not None:
    #         GLib.source_remove(self._update_source_id)
    #     super().destroy()


class BrightnessMaterial3(AnimatedScale):
    def __init__(self, device: str, service_instance, orientation="h", **kwargs):
        super().__init__(
            name="control-slider-mui",
            orientation=orientation,
            h_expand=True,
            has_origin=True,
            inverted=False if orientation == "h" else True,
            style_classes="" if orientation == "h" else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.service_instance = service_instance
        self.device = device
        self.current = 0
        self.max = 0
        self.percentage = 0
        self.exist = BACKLIGHT_SUPPORTED
        self.add_style_class("brightness")
        self.update_from_user = False
        self.ui_updating = False
        self.service_instance.connect("value-changed", self.update_brightness_slider)
        self.connect("change-value", self.set_brightness)

        # init
        self.init_brightness()

    def init_brightness(self):
        if self.exist:
            self.current = self.service_instance.get_brightness()
            self.max = self.service_instance.get_max_brightness()
            self.percentage = self.current / self.max
            self.update_brightness_slider(None, self.current, self.max)

    def update_brightness_slider(self, source, new_value, max_value):
        if max_value <= 0 or self.ui_updating:
            return

        self.ui_updating = True
        brightness = new_value / max_value
        if self.update_from_user:
            self.set_value(brightness)
        else:
            self.animate_value(brightness)
        self.update_from_user = False
        self.ui_updating = False

    def set_brightness(self, source, scroll_type, value):
        self.update_from_user = True
        new_value = int(value * 100)
        self.service_instance.set_brightness(new_value)
