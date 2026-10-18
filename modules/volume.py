from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox

from widgets.overrides import Svg
from widgets.material_label import MaterialIconLabel
from widgets.animated_scale import AnimatedScale, AnimatedCircularScale
from services.volume_service import VolumeService
from config.config import config
import svg
import icons

from gi.repository import Gdk  # type: ignore


class BaseAudioSlider(AnimatedScale):
    def __init__(self, name="control-slider", **kwargs):
        super().__init__(
            name=name,
            orientation="h" if not config.VERTICAL else "v",
            h_expand=True,
            has_origin=True,
            inverted=bool(config.VERTICAL),
            style_classes="" if not config.VERTICAL else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )

        self.add_style_class("vol")  # Shared style class
        self.is_muted = False
        self.volume_service = VolumeService()

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
            # Child classes will define self.mute_style (e.g., "muted-slider" vs "mic-off")
            self.add_style_class(self.mute_style)
            if self.max_value > max_val:
                self.remove_style_class("vol-overflow-slider")
        else:
            self.remove_style_class(self.mute_style)
            self.add_style_class("vol")
            if is_overflow and self.max_value > max_val:
                self.add_style_class("vol-overflow-slider")

    def update_volume(self, volume, overflow):
        if volume is not None:
            if self.min_value <= volume <= self.max_value:
                self.animate_value(volume)
            elif overflow and volume >= self.max_value:
                self.animate_value(self.max_value)


class VolumeSlider(BaseAudioSlider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mute_style = "muted-slider"
        self.volume_service.connect("speaker-volume-changed", self.on_value_changed)


class MicSlider(BaseAudioSlider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mute_style = "mic-off"
        self.volume_service.connect("mic-volume-changed", self.on_value_changed)


class BaseMaterial3Slider(AnimatedScale):
    def __init__(self, orientation="h", **kwargs):
        super().__init__(
            name="control-slider-mui",
            orientation=orientation,
            h_expand=True,
            has_origin=True,
            inverted=orientation != "h",
            style_classes="" if orientation == "h" else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )
        self.add_style_class("vol")  # Shared style class
        self.is_muted = False
        self.ui_updating = False
        self.is_dragging = False
        self.update_from_user = False
        self.volume_service = VolumeService()

        self.connect("change-value", self.set_volume_callback)
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
            logger.info(f"toggling mute {is_muted}")  # Fixed loguru formatting here
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
                self.add_style_class("vol-overflow-slider")
            else:
                self.remove_style_class("vol-overflow-slider")
            if not self.ui_updating:
                self.ui_updating = True
                if self.update_from_user or self.is_dragging:
                    self.set_value(volume)
                else:
                    self.animate_value(volume)
                self.update_from_user = False
                self.ui_updating = False

    def set_volume_callback(self, source, _, value):
        raise NotImplementedError


class VolumeMaterial3(BaseMaterial3Slider):
    def __init__(self, orientation="h", **kwargs):
        super().__init__(orientation=orientation, **kwargs)
        self.volume_service.connect("speaker-volume-changed", self.on_value_changed)

    def set_volume_callback(self, source, _, value):
        self.update_from_user = True
        self.volume_service.set_volume(value)


class MicMaterial3(BaseMaterial3Slider):
    def __init__(self, orientation="h", **kwargs):
        super().__init__(orientation=orientation, **kwargs)
        self.volume_service.connect("mic-volume-changed", self.on_value_changed)

    def set_volume_callback(self, source, _, value):
        self.update_from_user = True
        self.volume_service.set_mic_volume(value)


class BaseAudioSmall(Box):
    def __init__(self, name, bar_name, **kwargs):
        super().__init__(name=name, **kwargs)
        self.progress_bar = AnimatedCircularScale(
            name=bar_name,
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
        )
        self.scroll_accumulator = 0.0

        # child classes will initialize self.vol_label
        self.vol_label = None

        self.volume_service = VolumeService()
        self.hide_timer = None
        self.hover_counter = 0
        self.vol_popup_label = Label(name="control-slider-label", label="--")

    def _setup_event_box(self, button_name):
        self.vol_button = Button(
            name=button_name, on_clicked=self.toggle_mute_callback, child=self.vol_label
        )
        self.event_box = EventBox(
            name="eventer",
            v_expand=True,
            h_expand=True,
            events=["scroll", "smooth-scroll"],
            child=Overlay(child=self.progress_bar, overlays=self.vol_button),
        )
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add(self.event_box)

    def on_scroll(self, _, event):
        success, _delta_x, delta_y = event.get_scroll_deltas()
        DELTA = 0.05

        if success:
            self.scroll_accumulator += delta_y
            THRESHOLD = 1.0

            if self.scroll_accumulator >= THRESHOLD:
                curr_vol = self.get_current_level()
                self.set_level_callback(curr_vol - DELTA)
                self.scroll_accumulator = 0.0

            elif self.scroll_accumulator <= -THRESHOLD:
                curr_vol = self.get_current_level()
                self.set_level_callback(curr_vol + DELTA)
                self.scroll_accumulator = 0.0
        else:
            curr_vol = self.get_current_level()
            match event.direction:
                case Gdk.ScrollDirection.UP:
                    self.set_level_callback(curr_vol + DELTA)
                case Gdk.ScrollDirection.DOWN:
                    self.set_level_callback(curr_vol - DELTA)
        return True

    def update_volume(self, source, new_val, max_val, is_muted):
        if new_val is None:
            return

        self.progress_bar.animate_value(new_val)
        if is_muted:
            self.progress_bar.add_style_class("muted")
            self.vol_label.add_style_class("muted")
            self.set_muted_icon()
        else:
            self.progress_bar.remove_style_class("muted")
            self.vol_label.remove_style_class("muted")
            self.set_unmuted_icon()

    # to be implemented by child
    def toggle_mute_callback(self, event):
        raise NotImplementedError

    def get_current_level(self):
        raise NotImplementedError

    def set_level_callback(self, val):
        raise NotImplementedError

    def set_muted_icon(self):
        raise NotImplementedError

    def set_unmuted_icon(self):
        raise NotImplementedError


class VolumeSmall(BaseAudioSmall):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-vol", bar_name="button-volume", **kwargs)
        self.vol_label = Svg(name="vol-label", svg_string=svg.volume_modern)
        self._setup_event_box("vol-button")
        self.volume_service.connect("speaker-volume-changed", self.update_volume)

    def toggle_mute_callback(self, event):
        self.volume_service.toggle_mute()

    def get_current_level(self):
        return self.volume_service.get_current_volume()[0]

    def set_level_callback(self, val):
        self.volume_service.set_volume(val)

    def set_muted_icon(self):
        self.vol_label.set_from_string(svg.volume_mute_modern)

    def set_unmuted_icon(self):
        self.vol_label.set_from_string(svg.volume_modern)


class MicSmall(BaseAudioSmall):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-mic", bar_name="button-mic", **kwargs)
        self.vol_label = MaterialIconLabel(
            name="mic-label", icon_text=icons.mic.symbol()
        )
        self._setup_event_box("mic-button")
        self.volume_service.connect("mic-volume-changed", self.update_volume)

    def toggle_mute_callback(self, event):
        self.volume_service.toggle_mic_mute()

    def get_current_level(self):
        return self.volume_service.get_mic_status()[0]

    def set_level_callback(self, val):
        self.volume_service.set_mic_volume(val)

    def set_muted_icon(self):
        self.vol_label.set_icon(icons.mic_off.symbol())

    def set_unmuted_icon(self):
        self.vol_label.set_icon(icons.mic.symbol())
