from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer

from widgets.overrides import PatchedX11Window as Window

from modules.metrics import MetricsProvider
from modules.controls import ControlsManager

from widgets.material_label import MaterialIconLabel

from config.info import config
import icons


class LowBatteryBanner(Revealer):
    LOW_BATTERY_THRESHOLD = 15

    def __init__(self, **kwargs):
        super().__init__(
            name="notification-revealer",
            style="padding-top:6px",
            transition_duration=250,
            transition_type="slide-down",
            child_revealed=False,
            style_classes="vertical" if config.VERTICAL else "horizontal",
            **kwargs
        )

        self.provider = MetricsProvider()
        self.provider.connect("battery-changed", self.check_low_bat)

        self.dismissed = False
        self.low_bat_msg = Label(label="Low Battery fam (<15%)")

        self.content_box = Box(
            orientation="v",
            children=[
                Label(name="notification-source", label="ZENITH", h_align=True),
                self.low_bat_msg,
            ],
        )

        close_btn = Button(
            name="close-button",
            child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
            tooltip_text="Exit",
            on_clicked=lambda *_: self.close_notification(),
        )

        self.notification_box = Box(
            name="notification-box",
            style_classes="vertical" if config.VERTICAL else "horizontal",
            children=[
                MaterialIconLabel(name="notification-icon", h_align=True, icon_text=icons.blur.symbol()),
                Box(h_expand=True, children=self.content_box),
                Box(children=close_btn),
            ],
        )

        self.children = self.notification_box

        if config.VERTICAL:
            self.notification_box.remove_style_class("horizontal")

    def check_low_bat(self, _source, battery_percent: float, is_charging: bool):
        if not is_charging and battery_percent < self.LOW_BATTERY_THRESHOLD + 1:
            self.low_bat_msg.set_label(f"Low Battery fam (<{int(battery_percent)}%)")
            self.reveal_notification()
        else:
            self.hide_notification()

    def close_notification(self):
        self.hide_notification()
        self.dismissed = True

    def reveal_notification(self):
        if not self.dismissed:
            self.set_reveal_child(True)

    def hide_notification(self):
        self.dismissed = False
        self.set_reveal_child(False)


class TransientWindow(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notification-popup",
            layer="top",
            geometry="top",
            type_hint='notification',
            visible=False,
            **kwargs
        )

        self.controls = ControlsManager()

        self.revealers = [
            LowBatteryBanner(),
            self.controls.get_volume_revealer(),
            self.controls.get_volume_overflow_revealer(),
            self.controls.get_brightness_revealer(),
        ]

        for revealer in self.revealers:
            revealer.connect("notify::reveal-child", self._on_reveal_intent)
            revealer.connect("notify::child-revealed", self._on_reveal_finished)

        self.children = Box(
            orientation="v",
            children=[
                *self.revealers,
            ],
        )

    # reveal before revealer animation
    def _on_reveal_intent(self, revealer, _):
        if revealer.get_reveal_child():
            self.set_visible(True)

    # hide after revealer animation
    def _on_reveal_finished(self, revealer, _):
        if any(r.get_reveal_child() for r in self.revealers):
            return  # someone still wants to be visible

        if not any(r.get_child_revealed() for r in self.revealers):
            self.set_visible(False)

