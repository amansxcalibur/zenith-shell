from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer

import icons

from config.config import config
from config.info import IS_WAYLAND, SHELL_NAME
from config.i3.utils import glass_mode

from modules.controls import ControlsManager

from services.metrics import MetricsProvider

from utils.colors import bind_theme
from utils.helpers import keep_window, get_absolute_wayland_widget_position

from widgets.variable_font_label import VariableIconLabel

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window

from gi.repository import Gdk  # type: ignore


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
            **kwargs,
        )

        self.provider = MetricsProvider()
        self.provider.connect("battery-changed", self.check_low_bat)

        self.dismissed = False
        self.low_bat_msg = Label(name="notif-low-bat-msg", label="Low Battery (<15%)")

        self.content_box = Box(
            orientation="v",
            children=[
                Label(name="notification-source", label="ZENITH", h_align=True),
                self.low_bat_msg,
            ],
        )

        close_btn = Button(
            name="close-button-small",
            child=VariableIconLabel(
                name="close-label-small", icon_text=icons.material.close.symbol()
            ),
            tooltip_text="Exit",
            on_clicked=lambda *_: self.close_notification(),
        )

        self.notification_box = Box(
            name="notification-box",
            style_classes="vertical" if config.VERTICAL else "horizontal",
            children=[
                VariableIconLabel(
                    name="notification-icon",
                    h_align=True,
                    icon_text=icons.material.blur.symbol(),
                ),
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
    MARGIN = 14

    def __init__(self, shell_window=None, **kwargs):
        # the OSD hangs off this window
        self._shell_window = shell_window
        if IS_WAYLAND:
            super().__init__(
                name="notification-popup",
                title=f"{SHELL_NAME}-osd",  # the layer namespace swayfx blurs
                layer="overlay",
                keyboard_mode="on-demand",
                anchor="top left",
                exclusivity="none",
                margin=(0, 0, 0, 0),
                visible=False,
                **kwargs,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)
        else:
            super().__init__(
                name="notification-popup",
                layer="top",
                geometry="top",
                type_hint="notification",
                visible=False,
                **kwargs,
            )
            # disconnect the X11Window geometry enforcement hook
            if self._size_allocate_hook:
                self.handler_disconnect(self._size_allocate_hook)
                self._size_allocate_hook = None

        bind_theme(self)
        if glass_mode():
            self.add_style_class("glass")
        
        self.connect("delete-event", lambda *_: keep_window(self))

        self.controls = ControlsManager()

        self.revealers = [
            LowBatteryBanner(),
            self.controls.get_volume_revealer(),
            self.controls.get_volume_overflow_revealer(),
            self.controls.get_brightness_revealer(),
            self.controls.get_mic_revealer(),
        ]

        for revealer in self.revealers:
            revealer.connect("notify::reveal-child", self._on_reveal_intent)
            revealer.connect("notify::child-revealed", self._on_reveal_finished)

        # follow the pill as it resizes or gets dragged, and our own size
        self.connect("size-allocate", lambda *_: self._follow_shell_position())
        if shell_window is not None:
            shell_window.connect(
                "size-allocate", lambda *_: self._follow_shell_position()
            )
            shell_window.connect("on-drag", lambda *_: self._follow_shell_position())

        self.children = Box(
            orientation="v",
            style="min-height:1px",
            children=[
                *self.revealers,
            ],
        )

    # reveal before revealer animation
    def _on_reveal_intent(self, revealer, _):
        if revealer.get_reveal_child():
            if not self.get_visible():
                self._follow_shell_monitor()
            self.set_visible(True)
            self._follow_shell_position()

    def _follow_shell_monitor(self):
        if not IS_WAYLAND or self._shell_window is None:
            return
        win = self._shell_window.get_window()
        if win is None:
            return
        monitor = Gdk.Display.get_default().get_monitor_at_window(win)
        if monitor is not None:
            # fabric's `monitor` property is an int and drops a Gdk.Monitor
            GtkLayerShell.set_monitor(self, monitor)

    def _follow_shell_position(self):
        pill = self._shell_window
        if pill is None or not self.get_visible():
            return
        pill_alloc = pill.get_allocation()
        own_w, own_h = self.get_allocated_width(), self.get_allocated_height()
        at_bottom = config.get("top_pill.POSITION.y") == "bottom"

        win = pill.get_window()
        if win is None:
            return
        geo = Gdk.Display.get_default().get_monitor_at_window(win).get_geometry()

        if IS_WAYLAND:
            ok, pill_x, pill_y = get_absolute_wayland_widget_position(pill)
            if not ok:
                return
            pill_x, pill_y = pill_x - geo.x, pill_y - geo.y
            min_x, min_y = 0, 0
        else:
            pill_x, pill_y = pill.get_position()
            min_x, min_y = geo.x, geo.y

        # keep it on screen when the pill hugs a side
        x = pill_x + (pill_alloc.width - own_w) // 2
        x = max(min_x + self.MARGIN, min(x, min_x + geo.width - own_w - self.MARGIN))
        y = pill_y - own_h if at_bottom else pill_y + pill_alloc.height
        y = max(min_y, y)

        if IS_WAYLAND:
            if GtkLayerShell.get_margin(self, GtkLayerShell.Edge.LEFT) != x:
                GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, x)
            if GtkLayerShell.get_margin(self, GtkLayerShell.Edge.TOP) != y:
                GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, y)
        elif self.get_position() != (x, y):
            self.move(x, y)

    # hide after revealer animation
    def _on_reveal_finished(self, revealer, _):
        if any(r.get_reveal_child() for r in self.revealers):
            return  # someone still wants to be visible

        if not any(r.get_child_revealed() for r in self.revealers):
            self.set_visible(False)
