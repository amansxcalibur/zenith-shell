from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
from fabric.widgets.x11 import X11Window as Window

from metrics import MetricsProvider
import info
import icons.icons as icons

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib


class Notification(Revealer):
    LOW_BATTERY_THRESHOLD = 15

    def __init__(self, **kwargs):
        super().__init__(
            name="notification-revealer",
            transition_duration=250,
            transition_type="slide-down",
            child_revealed=False,
            style_classes="vertical" if info.VERTICAL else "horizontal",
            **kwargs
        )

        self.provider = MetricsProvider()
        self.provider.connect("battery-changed", self.check_low_bat)

        self.warning_shown = False
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
            child=Label(name="close-label", markup=icons.cancel),
            tooltip_text="Exit",
            on_clicked=lambda *_: self.close_notification(),
        )

        self.notification_box = Box(
            name="notification-box",
            style_classes="vertical" if info.VERTICAL else "horizontal",
            children=[
                Label(name="notification-icon", h_align=True, markup=icons.blur),
                Box(h_expand=True, children=self.content_box),
                Box(children=close_btn),
            ],
        )

        self.children = self.notification_box

        if info.VERTICAL:
            self.notification_box.remove_style_class("horizontal")

    def check_low_bat(self, _source, battery_percent: float, is_charging: bool):
        if not is_charging and battery_percent < self.LOW_BATTERY_THRESHOLD:
            self.reveal_notification()
        else:
            self.hide_notification()

    def close_notification(self):
        self.hide_notification()
        self.warning_shown = True

    def reveal_notification(self):
        if not self.warning_shown:
            self.set_reveal_child(True)

    def hide_notification(self):
        self.warning_shown = False
        self.set_reveal_child(False)


class NotificationPopup(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notification-popup",
            layer="top",
            keyboard_mode="none",
            exclusivity="none",
            type_hint="notification",
            visible=True,
            all_visible=True,
            **kwargs
        )
        self.children = Box(style="min-height: 1px;", children=Notification())
