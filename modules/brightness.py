import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk  # type: ignore

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox

from config.config import config
from widgets.material_label import MaterialIconLabel
from widgets.animated_scale import AnimatedScale, AnimatedCircularScale
from services.brightness_service import BrightnessService
import icons


def supports_backlight():
    try:
        output = (
            subprocess.check_output(["brightnessctl", "-l"]).decode("utf-8").lower()
        )
        return "backlight" in output
    except Exception:
        return False


BACKLIGHT_SUPPORTED = supports_backlight()


class BaseBrightnessSlider(AnimatedScale):
    def __init__(self, device: str, service_instance: BrightnessService, **kwargs):
        super().__init__(increments=(0.01, 0.1), **kwargs)

        self.service_instance = service_instance
        self.device = device
        self.exist = BACKLIGHT_SUPPORTED
        self.add_style_class("brightness")

        self.update_from_user = False
        self.ui_updating = False

        self.service_instance.connect("value-changed", self.update_brightness_slider)
        self.connect("change-value", self.set_brightness)

        self.init_brightness()

    def init_brightness(self):
        if self.exist:
            current = self.service_instance.get_brightness()
            max_val = self.service_instance.get_max_brightness()
            self.update_brightness_slider(None, current, max_val)

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


class BrightnessSlider(BaseBrightnessSlider):
    def __init__(self, device: str, service_instance: BrightnessService, **kwargs):
        super().__init__(
            device=device,
            service_instance=service_instance,
            name="control-slider",
            orientation="h" if not config.VERTICAL else "v",
            h_expand=True,
            has_origin=True,
            inverted=bool(config.VERTICAL),
            style_classes="" if not config.VERTICAL else "vertical",
            **kwargs,
        )


class BrightnessMaterial3(BaseBrightnessSlider):
    def __init__(
        self,
        device: str,
        service_instance: BrightnessService,
        orientation="h",
        **kwargs,
    ):
        super().__init__(
            device=device,
            service_instance=service_instance,
            name="control-slider-mui",
            orientation=orientation,
            h_expand=True,
            has_origin=True,
            inverted=orientation != "h",
            style_classes="" if orientation == "h" else "vertical",
            **kwargs,
        )


class BrightnessSmall(Box):
    def __init__(self, device: str, service_instance: BrightnessService, **kwargs):
        super().__init__(name="button-bar-brightness", **kwargs)
        self.service_instance = service_instance
        self.device = device
        self.exist = BACKLIGHT_SUPPORTED
        self.scroll_accumulator = 0.0

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
            events=["scroll", "smooth-scroll"],
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
            current = self.service_instance.get_brightness()
            max_val = self.service_instance.get_max_brightness()
            self.on_brightness_changed(self, current, max_val)

    def on_scroll(self, widget, event):
        success, _delta_x, delta_y = event.get_scroll_deltas()

        if success:
            self.scroll_accumulator += delta_y
            THRESHOLD = 1.0

            if self.scroll_accumulator >= THRESHOLD:
                self.service_instance.decrement_brightness()
                self.scroll_accumulator = 0.0

            elif self.scroll_accumulator <= -THRESHOLD:
                self.service_instance.increment_brightness()
                self.scroll_accumulator = 0.0

        else:
            match event.direction:
                case Gdk.ScrollDirection.UP:
                    self.service_instance.increment_brightness()
                case Gdk.ScrollDirection.DOWN:
                    self.service_instance.decrement_brightness()

        return True

    def on_brightness_changed(self, source, new_value, max_value):
        if max_value > 0:
            percentage = new_value / max_value
            self.progress_bar.animate_value(percentage)
