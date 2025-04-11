import subprocess
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.circularprogressbar import CircularProgressBar
import icons.icons as icons
import info

from gi.repository import GLib

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
            orientation="h" if not info.VERTICAL else 'v',
            h_expand=True,
            has_origin=True,
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.add_style_class("vol")
        volume, _ = get_current_volume()
        # self.update_volume_slider(volume, False)
        # self.connect("value-changed", self.on_value_changed)

    # def on_value_changed(self, _):
    #     new_volume = int(self.value * 100)
        # subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{new_volume}%"])
        # self.update_volume()

    def update_volume_slider(self, volume, overflow):
        """Update slider based on current volume."""
        # volume, _ = get_current_volume()
        print(volume)
        if volume is not None:
            if overflow:
                self.value = max(0, (volume - 100) / 100)
            else:
                self.value = min(1, volume / 100) 

class VolumeSmall(Box):
    def __init__(self, slider_instance, overflow_instance, **kwargs):
        super().__init__(name="button-bar-vol", **kwargs)
        self.progress_bar = CircularProgressBar(
            name="button-volume", 
            size=28, 
            line_width=2,
            start_angle=-90,
            end_angle=270,
        )

        self.vol_label = Label(name="vol-label", markup=icons.vol_high)

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
        self.hide_timer = None
        self.hover_counter = 0
        self.vol_revealer = slider_instance
        self.vol_overflow_revealer = overflow_instance
        # self.vol_event = EventBox(
        #     name="eventer",
        #     v_expand=True,
        #     h_expand=True,
        #     events="scroll",
        #     child=Overlay(
        #         child=self.vol_revealer,
        #         # overlays=self.vol_button
        #     ),
        # )
        # self.vol_event.get_child().connect("scroll-event", self.on_scroll)
        # self.vol_overflow_revealer.get_child().connect("scroll-event", self.on_scroll)
        # self.f = EventBox(events="")
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add(self.event_box)
        self.update_volume_widget()

    def toggle_mute(self, event):
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        self.update_volume_widget()

    # def on_slider_scroll(self, _, event):
    #     val_y = event.delta_y

    #     if val_y > 0:
    #         subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"])
    #     else:
    #         subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"])
    
    def on_scroll(self, _, event):
        """Increase or decrease volume using scroll wheel."""
        match event.direction:
            case 0:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"])
            case 1:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"])
        self.update_volume_widget()
    
    def reveal_revealer(self):
        self.hover_counter += 1
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        # Reveal levels on hover for all metrics
        self.vol_revealer.set_reveal_child(True)
        self.vol_overflow_revealer.set_reveal_child(True)
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
        self.vol_revealer.set_reveal_child(False)
        self.vol_overflow_revealer.set_reveal_child(False)
        self.hide_timer = None
        return False

    def update_volume_widget(self):
        """Update the UI elements based on the current volume."""
        volume, muted = get_current_volume()
        # self.vol_revealer.set_reveal_child(True)

        self.reveal_revealer()
        if volume > 100:
            # if self.vol_overflow_revealer.get_child().value != (volume - 100) / 100:
            self.vol_overflow_revealer.get_child().update_volume_slider(volume, overflow=True)
            self.vol_overflow_revealer.set_reveal_child(True)
            self.vol_revealer.set_reveal_child(False)
        else:
            # if self.vol_revealer.get_child().value != volume / 100:
            self.vol_revealer.get_child().update_volume_slider(volume, overflow=False)
            self.vol_revealer.set_reveal_child(True)
            self.vol_overflow_revealer.set_reveal_child(False)
        self.await_hide()
        
        if volume is None:
            return
        
        self.progress_bar.value = volume / 100

        if muted:
            self.vol_overflow_revealer.get_child().remove_style_class("vol")
            self.vol_overflow_revealer.get_child().remove_style_class("vol-overflow-slider")
            self.vol_revealer.get_child().remove_style_class("vol")

            self.vol_revealer.get_child().add_style_class("muted-slider")
            self.vol_overflow_revealer.get_child().add_style_class("muted-slider")
            self.progress_bar.add_style_class("muted")
            self.vol_label.add_style_class("muted")

            self.vol_button.get_child().set_markup(icons.vol_off)
            self.set_tooltip_text("Muted")
        else:
            self.vol_revealer.get_child().remove_style_class("muted-slider")
            self.vol_overflow_revealer.get_child().remove_style_class("muted-slider")
            self.progress_bar.remove_style_class("muted")
            self.vol_label.remove_style_class("muted")

            self.vol_overflow_revealer.get_child().add_style_class("vol-overflow-slider")
            self.vol_revealer.get_child().add_style_class("vol")
            self.vol_overflow_revealer.get_child().add_style_class("vol")

            self.set_tooltip_text(f"{volume}%")

            if volume > 74:
                self.vol_button.get_child().set_markup(icons.vol_high)
                # print("High", volume)
            elif volume > 0:
                self.vol_button.get_child().set_markup(icons.vol_medium)
                # print("Medium")
            else:
                self.vol_button.get_child().set_markup(icons.vol_mute)
                # print("Mute")
