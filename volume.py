import subprocess
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.circularprogressbar import CircularProgressBar
import icons.icons as icons

from gi.repository import GLib

def supports_backlight():
    try:
        output = subprocess.check_output(["brightnessctl", "-l"]).decode("utf-8").lower()
        return "backlight" in output
    except Exception:
        return False

BACKLIGHT_SUPPORTED = supports_backlight()

import subprocess

def get_current_volume():
    try:
        output = subprocess.run(
            "pactl get-sink-volume @DEFAULT_SINK@ | awk '{print $5}' | tr -d '%'", 
            shell=True, text=True, capture_output=True, check=True
        )
        volume_percent = int(output.stdout.strip()) if output.stdout.strip().isdigit() else None

        output_mute = subprocess.run(
            "pactl get-sink-mute @DEFAULT_SINK@", 
            shell=True, text=True, capture_output=True, check=True
        )
        is_muted = "yes" in output_mute.stdout.lower()

        return volume_percent, is_muted
    except subprocess.CalledProcessError:
        return None, None

volume, muted = get_current_volume()
print(f"Volume: {volume}% | Muted: {muted}")


class VolumeSlider(Scale):
    def __init__(self, **kwargs):
        super().__init__(
            name="control-slider",
            orientation="h",
            h_expand=True,
            has_origin=True,
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.add_style_class("vol")
        self.update_volume()
        self.connect("value-changed", self.on_value_changed)

    def on_value_changed(self, _):
        new_volume = int(self.value * 100)
        # subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{new_volume}%"])
        self.update_volume()

    def update_volume(self):
        """Update slider based on current volume."""
        volume, _ = get_current_volume()
        print(volume)
        if volume is not None:
            self.value = volume / 100

class VolumeSmall(Box):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-vol", **kwargs)
        self.progress_bar = CircularProgressBar(
            name="button-volume", size=28, line_width=2,
            start_angle=150, end_angle=390,
        )
        self.vol_label = Label(name="vol-label", markup=icons.vol_high)
        # self.vol_label = Label(name="vol-label", label="H")
        self.vol_button = Button(
            name="vol-button",
            on_clicked=self.toggle_mute,
            child=self.vol_label
        )
        self.event_box = EventBox(
            name="eventer",
            v_expand=True,
            h_expand=True,
            events="scroll",
            child=Overlay(
                child=self.progress_bar,
                overlays=self.vol_button
            ),
        )
        # self.event_box.connect("scroll-event", self.on_scroll)
        self.add(self.event_box)
        self.update_volume_widget()

    def toggle_mute(self, event):
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        self.update_volume_widget()

    # def on_scroll(self, _, event):
    #     """Increase or decrease volume using scroll wheel."""
    #     match event.direction:
    #         case 0:
    #             subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+2%"])
    #         case 1:
    #             subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-2%"])
    #     self.update_volume_widget()

    def update_volume_widget(self):
        """Update the UI elements based on the current volume."""
        volume, muted = get_current_volume()
        if volume is None:
            return

        if muted:
            self.vol_button.get_child().set_markup(icons.vol_off)
            # self.vol_button.get_child().set_label("M")
            self.progress_bar.add_style_class("muted")
            self.vol_label.add_style_class("muted")
            self.set_tooltip_text("Muted")
        else:
            # self.vol_button.get_child().set_label("H")
            self.progress_bar.remove_style_class("muted")
            self.vol_label.remove_style_class("muted")
            self.set_tooltip_text(f"{volume}%")
            self.progress_bar.value = volume / 100

            if volume > 74:
                self.vol_button.get_child().set_markup(icons.vol_high)
                # print("High", volume)
            elif volume > 0:
                self.vol_button.get_child().set_markup(icons.vol_medium)
                # print("Medium")
            else:
                self.vol_button.get_child().set_markup(icons.vol_mute)
                # print("Mute")
