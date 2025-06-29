from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from fabric.widgets.button import Button
from fabric.widgets.scale import Scale
from fabric.utils.helpers import exec_shell_command_async
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk
import icons.icons as icons
import subprocess
import re
import info


def supports_backlight():
    try:
        output = (
            subprocess.check_output(["brightnessctl", "-l"]).decode("utf-8").lower()
        )
        return "backlight" in output
    except Exception:
        return False


BACKLIGHT_SUPPORTED = supports_backlight()


class BrightnessSlider(Scale):
    def __init__(self, **kwargs):
        super().__init__(
            name="control-slider",
            orientation="h" if not info.VERTICAL else "v",
            h_expand=True,
            has_origin=True,
            inverted=True if info.VERTICAL else False,
            style_classes="" if not info.VERTICAL else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.add_style_class("brightness")
        self.connect("value-changed", self.set_brightness)

    def update_brightness_slider(self, brightness):
        self.value = brightness / 100

    def set_brightness(self, source):
        new_value = int(source.get_value() * 100)
        print("new val", new_value)
        exec_shell_command_async(f"brightnessctl set {new_value}%")
        # too lazy to change this
        exec_shell_command_async(
            f"fabric-cli exec bar-example 'notch.controls.brightness_small.update_brightness()'"
        )
        self.update_brightness_slider(new_value)


class BrightnessSmall(Box):
    def __init__(self, device: str, slider_instance, **kwargs):
        super().__init__(name="button-bar-brightness", **kwargs)
        # self.brightness = Brightness.get_initial()
        # if self.brightness.screen_brightness == -1:
        #     self.destroy()
        #     return
        self.device = device
        self.current = 0
        self.max = 0
        self.percentage = 0
        self.exist = supports_backlight
        self.brightness_revealer_ref = slider_instance
        self.hide_timer = None
        self.hover_counter = 0

        self.progress_bar = CircularProgressBar(
            name="button-brightness",
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
        )
        self.brightness_label = Label(name="brightness-label", markup=icons.brightness)
        self.brightness_button = Button(
            name="brightness-button", child=self.brightness_label
        )
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
        self.update_brightness()

        # self._updating_from_brightness = False
        # self._pending_value = None
        # self._update_source_id = None

        # self.progress_bar.connect("notify::value", self.on_progress_value_changed)
        # self.brightness.connect("screen", self.on_brightness_changed)
        # self.on_brightness_changed()

    def update_brightness(self):
        if self.exist:
            init = (
                subprocess.check_output(["brightnessctl", "-d", self.device])
                .decode("utf-8")
                .lower()
            )
            self.current = int(re.search(r"current brightness:\s+(\d+)", init).group(1))
            self.max = int(re.search(r"max brightness:\s+(\d+)", init).group(1))
            self.percentage = int(re.search(r"\((\d+)%\)", init).group(1))
            self.on_brightness_changed()

    def on_scroll(self, widget, event):
        print("here ", event.direction)
        match event.direction:
            case 0:
                subprocess.run(["brightnessctl", "set", "+5%"])
            case 1:
                subprocess.run(["brightnessctl", "set", "5%-"])
        self.update_brightness()

    # def on_scroll(self, widget, event):
    #     if self.brightness.max_screen == -1:
    #         return

    #     step_size = 5
    #     current_norm = self.progress_bar.value
    #     if event.delta_y < 0:
    #         new_norm = min(current_norm + (step_size / self.brightness.max_screen), 1)
    #     elif event.delta_y > 0:
    #         new_norm = max(current_norm - (step_size / self.brightness.max_screen), 0)
    #     else:
    #         return
    #     self.progress_bar.value = new_norm

    # def on_progress_value_changed(self, widget, pspec):
    #     if self._updating_from_brightness:
    #         return
    #     new_norm = widget.value
    #     new_brightness = int(new_norm * self.brightness.max_screen)
    #     self._pending_value = new_brightness
    #     if self._update_source_id is None:
    #         self._update_source_id = GLib.timeout_add(50, self._update_brightness_callback)

    # def _update_brightness_callback(self):
    #     if self._pending_value is not None and self._pending_value != self.brightness.screen_brightness:
    #         self.brightness.screen_brightness = self._pending_value
    #         self._pending_value = None
    #         return True
    #     else:
    #         self._update_source_id = None
    #         return False

    def reveal_revealer(self):
        self.hover_counter += 1
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        self.brightness_revealer_ref.set_reveal_child(True)
        return False

    def await_hide(self):
        if self.hover_counter > 0:
            self.hover_counter -= 1
        if self.hover_counter == 0:
            if self.hide_timer is not None:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(1000, self.hide_revealer)
        return False

    def hide_revealer(self):
        self.brightness_revealer_ref.set_reveal_child(False)
        self.hide_timer = None
        return False

    def on_brightness_changed(self, *args):
        # if self.brightness.max_screen == -1:
        #     return
        # normalized = self.brightness.screen_brightness / self.brightness.max_screen
        # self._updating_from_brightness = True
        # self.progress_bar.value = normalized
        # self.progress_bar.value = self.percentage/100
        self.progress_bar.value = self.percentage / 100
        self.reveal_revealer()
        self.brightness_revealer_ref.get_child().update_brightness_slider(
            self.percentage
        )
        self.await_hide()
        # self._updating_from_brightness = False

        # brightness_percentage = int(normalized * 100)
        brightness_percentage = self.percentage
        self.brightness_label.set_markup(icons.brightness)
        self.brightness_button.add_style_class("brightness-adjust")
        # if brightness_percentage >= 75:
        #     self.brightness_label.set_markup(icons.brightness_high)
        # elif brightness_percentage >= 24:
        #     self.brightness_label.set_markup(icons.brightness_medium)
        # else:
        #     self.brightness_label.set_markup(icons.brightness_low)
        self.set_tooltip_text(f"{brightness_percentage}%")

    # def destroy(self):
    #     if self._update_source_id is not None:
    #         GLib.source_remove(self._update_source_id)
    #     super().destroy()


class BrightnessMaterial3(Scale):
    def __init__(self, device: str, **kwargs):
        super().__init__(
            name="control-slider-mui",
            orientation="h",
            h_expand=True,
            has_origin=True,
            inverted=False,
            style_classes="" if not info.VERTICAL else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.device = device
        self.current = 0
        self.max = 0
        self.percentage = 0
        self.exist = supports_backlight
        self.hide_timer = None
        self.hover_counter = 0
        self.add_style_class("brightness")
        self.update_brightness()
        self.connect("value-changed", self.set_brightness)

    def update_brightness(self):
        if self.exist:
            init = (
                subprocess.check_output(["brightnessctl", "-d", self.device])
                .decode("utf-8")
                .lower()
            )
            self.current = int(re.search(r"current brightness:\s+(\d+)", init).group(1))
            self.max = int(re.search(r"max brightness:\s+(\d+)", init).group(1))
            self.percentage = int(re.search(r"\((\d+)%\)", init).group(1))
            self.update_brightness_slider(self.percentage)

    def update_brightness_slider(self, brightness):
        self.value = brightness / 100

    def set_brightness(self, source):
        new_value = int(source.get_value() * 100)
        print("new val", new_value)
        exec_shell_command_async(f"brightnessctl set {new_value}%")
        # too lazy to change this
        # todo: add signals to brightness small and pass it to the sliders instead of the other way around
        exec_shell_command_async(
            f"fabric-cli exec bar-example 'notch.controls.brightness_small.update_brightness()'"
        )
        self.update_brightness_slider(new_value)
