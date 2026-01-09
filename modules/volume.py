from fabric.widgets.box import Box
from fabric.widgets.svg import Svg
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox

from widgets.animated_scale import AnimatedScale, AnimatedCircularScale, WigglyCircularScale
from services.volume_service import VolumeService
import svg
from config.info import config, HOME_DIR
from utils.colors import get_css_variable


class VolumeSlider(AnimatedScale):
    def __init__(self, **kwargs):
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

        self.add_style_class("vol")
        self.is_muted = False
        self.volume_service = VolumeService()
        self.volume_service.connect("value-changed", self.on_value_changed)

    def on_value_changed(self, source, new_val, max_val, is_muted):
        is_overflow = new_val > max_val
        if self.is_muted != is_muted:
            self.is_muted = is_muted
            self.handle_mute_toggle(is_muted, is_overflow, max_val)

        if new_val != self.value:
            self.update_volume(new_val, is_overflow)

    def handle_mute_toggle(self, is_muted, is_overflow, max_val):
        if is_muted:
            self.remove_style_class("vol")
            self.add_style_class("muted-slider")
            if self.max_value > max_val:
                self.remove_style_class("vol-overflow-slider")
        else:
            self.remove_style_class("muted-slider")
            self.add_style_class("vol")
            if is_overflow and self.max_value > max_val:
                self.add_style_class("vol-overflow-slider")

    def update_volume(self, volume, overflow):
        if volume is not None:
            if self.min_value <= volume <= self.max_value:
                self.animate_value(volume)
            elif overflow and volume >= self.max_value:
                self.animate_value(self.max_value)


class VolumeMaterial3(AnimatedScale):
    def __init__(self, orientation="h", **kwargs):
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
        self.add_style_class("vol")
        self.is_muted = False
        self.ui_updating = False
        self.is_dragging = False
        self.update_from_user = False

        self.volume_service = VolumeService()

        self.volume_service.connect("value-changed", self.on_value_changed)
        self.connect("change-value", self.set_volume)

        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)

    def on_button_press(self, widget, event):
        self.is_dragging = True
        return False

    def on_button_release(self, widget, event):
        self.is_dragging = False
        return False

    def on_value_changed(self, source, new_val, max_val, is_muted):
        if self.is_muted != is_muted:
            print("toggling mute", is_muted)
            self.is_muted = is_muted
            self.handle_mute_toggle(is_muted)
        self.update_volume(new_val, is_muted)

    def handle_mute_toggle(self, is_muted):
        if is_muted:
            self.remove_style_class("vol")
            self.add_style_class("mute")
        else:
            self.remove_style_class("mute")
            self.add_style_class("vol")

    def update_volume(self, volume, is_muted):
        if volume is not None:
            if volume > 1 and not is_muted:
                self.add_style_class('vol-overflow-slider')
            else:
                self.remove_style_class('vol-overflow-slider')
            if not self.ui_updating:
                self.ui_updating = True
                if self.update_from_user or self.is_dragging:
                    self.set_value(volume)
                else:
                    self.animate_value(volume)
                self.update_from_user = False
                self.ui_updating = False

    def set_volume(self, source, _, value):
        self.update_from_user = True
        self.volume_service.set_volume(value)


class VolumeSmall(Box):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-vol", **kwargs)
        self.progress_bar = AnimatedCircularScale(
            name="button-volume",
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
        )

        # self.vol_label = Label(name="vol-label", markup=icons.vol_high)
        self.vol_label = Svg(name="vol-label", svg_string=svg.volume_modern, style="color:antiquewhite")
        self.vol_button = Button(
            name="vol-button", on_clicked=self.toggle_mute, child=self.vol_label
        )
        self.event_box = EventBox(
            name="eventer",
            v_expand=True,
            h_expand=True,
            events="scroll",
            child=Overlay(child=self.progress_bar, overlays=self.vol_button),
        )
        self.hide_timer = None
        self.hover_counter = 0
        self.vol_popup_label = Label(name="control-slider-label", label="--")
        
        self.event_box.connect("scroll-event", self.on_scroll)

        self.add(self.event_box)

        self.volume_service = VolumeService()
        self.volume_service.connect("value-changed", self.update_volume)

    def toggle_mute(self, event):
        self.volume_service.toggle_mute()

    def on_scroll(self, _, event):
        curr_vol, _ = self.volume_service.get_current_volume()
        DELTA = 0.05
        match event.direction:
            case 0:
                self.volume_service.set_volume(curr_vol + DELTA)
            case 1:
                self.volume_service.set_volume(curr_vol - DELTA)

    def update_volume(self, source, new_val, max_val, is_muted):
        volume, muted = new_val, is_muted

        if volume is None:
            return

        self.progress_bar.animate_value(volume)

        if muted:
            self.progress_bar.add_style_class("muted")
            # self.vol_label.add_style_class("muted")
            color = get_css_variable(file_path=f"{HOME_DIR}/fabric/styles/colors.css", var_name='outline')
            self.vol_label.set_style(f"color: {color}")
            self.vol_label.set_from_string(svg.volume_mute_modern)
        else:
            self.progress_bar.remove_style_class("muted")
            # self.vol_label.remove_style_class("muted")
            self.vol_label.set_style('color:antiquewhite;')
            self.vol_label.set_from_string(svg.volume_modern)

            # if volume > 74:
            #     self.vol_button.get_child().set_markup(icons.vol_high)
            # elif volume > 0:
            #     self.vol_button.get_child().set_markup(icons.vol_medium)
            # else:
            #     self.vol_button.get_child().set_markup(icons.vol_mute)
