import fabric
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.datetime import DateTime
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window

from modules.controls import ControlsManager
from modules.metrics import MetricsSmall, Battery
from modules.systray import SystemTray
from modules.workspaces import Workspaces
from utils.helpers import toggle_config_vertical_flag
import config.info as info
import icons.icons as icons

from utils.cursor import add_hover_cursor

from i3ipc import Connection
import subprocess


class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="top" if not info.VERTICAL else "bottom",
            geometry="top" if not info.VERTICAL else "left",
            type_hint="normal" if info.VERTICAL else "dock",
            margin="0px 0px 0px 0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )

        self.i3 = Connection()
        if info.VERTICAL:
            self.i3.command("gaps left all set 44px")
            self.i3.command("gaps top all set 3px")
        else:
            self.i3.command("gaps left all set 3px")
            self.i3.command("gaps top all set 0px")

        self.notch = kwargs.get("notch", None)

        if not info.VERTICAL:
            self.workspaces = Workspaces()
        else:
            self.controls = ControlsManager(notch=self.notch)
            self.vol_small = self.controls.get_volume_small()
            self.brightness_small = self.controls.get_brightness_small()

        self.systray = SystemTray()
        self.systray._update_visibility()
        if info.VERTICAL:  # for cases where the notch overlaps
            self.systray_revealer = Revealer(
                child=Box(orientation="v", spacing=3, children=[self.systray]),
                child_revealed=True,
                transition_type="slide-down",
            )

        self.date_time = Box(
            name="date-time-container",
            style_classes="" if not info.VERTICAL else "vertical",
            children=DateTime(
                name="date-time",
                formatters=["%H\n%M"] if info.VERTICAL else ["%H:%M"],
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
                style_classes="" if not info.VERTICAL else "vertical",
            ),
        )

        self.vertical_toggle_btn = Button(
            name="orientation-btn",
            child=Label(
                name="orientation-label",
                markup=(
                    icons.toggle_vertical
                    if not info.VERTICAL
                    else icons.toggle_horizontal
                ),
            ),
            on_clicked=lambda b, *_: self.toggle_vertical(),
        )

        self.metrics = MetricsSmall()
        if info.VERTICAL:  # for cases where the notch overlaps
            self.metrics_vertical_toggle_revealer = Revealer(
                child=Box(
                    orientation="v",
                    spacing=3,
                    children=[self.vertical_toggle_btn, self.metrics],
                ),
                child_revealed=True,
                transition_type="slide-up",
            )
        self.battery = Battery()

        add_hover_cursor(self.vertical_toggle_btn)

        self.main_bar = CenterBox(
            name="main-bar",
            orientation="h" if not info.VERTICAL else "v",
            h_align="fill" if not info.VERTICAL else "center",
            v_align="center" if not info.VERTICAL else "fill",
            style_classes="horizontal" if not info.VERTICAL else "vertical",
            start_children=Box(
                name="start-container",
                spacing=3,
                orientation="h" if not info.VERTICAL else "v",
                children=(
                    [self.vertical_toggle_btn, self.workspaces]
                    if not info.VERTICAL
                    else [
                        self.date_time,
                        Box(
                            name="vol-brightness-container",
                            orientation="v",
                            children=[self.vol_small, self.brightness_small],
                        ),
                        self.systray_revealer,
                    ]
                ),
            ),
            end_children=Box(
                name="end-container",
                spacing=3,
                orientation="h" if not info.VERTICAL else "v",
                children=(
                    [
                        self.systray,
                        self.metrics,
                        self.battery,
                        self.date_time,
                    ]
                    if not info.VERTICAL
                    else [self.metrics_vertical_toggle_revealer, self.battery]
                ),
            ),
        )

        if not info.VERTICAL:
            # main_bar gets class vertical for some reason
            self.main_bar.remove_style_class("vertical")

        self.ghost_bar = Box()

        self.visibility_stack = Stack(
            h_expand=True,
            v_expand=True,
            transition_type="over-down",
            transition_duration=100,
            children=[self.main_bar, self.ghost_bar],
        )

        self.children = self.visibility_stack
        self.hidden = False
        # self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        # self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    def toggle_vertical(self):
        toggle_config_vertical_flag()
        # restart bar
        subprocess.run([f"{info.HOME_DIR}/i3scripts/flaunch.sh"])
    
    def hide_bar_toggle(self):
        # this function runs through i3 keybindings
        if self.visibility_stack.get_visible_child() == self.main_bar:
            if info.VERTICAL:
                self.i3.command("gaps outer all set 3px")
            self.main_bar.add_style_class("hide-main-bar")
            self.notch.full_notch.add_style_class("hide-notch")

            self.visibility_stack.set_visible_child(self.ghost_bar)
            self.notch.visibility_stack.set_visible_child(self.notch.hidden_notch)
        else:
            if info.VERTICAL:
                self.i3.command("gaps left all set 44px")
                self.i3.command("gaps top all set 3px")
            self.main_bar.remove_style_class("hide-main-bar")
            self.notch.full_notch.remove_style_class("hide-notch")

            self.visibility_stack.set_visible_child(self.main_bar)
            self.notch.visibility_stack.set_visible_child(self.notch.full_notch)

    def hide_overlapping_modules(self):
        self.metrics_vertical_toggle_revealer.set_reveal_child(False)
        self.systray_revealer.set_reveal_child(False)

    def reveal_overlapping_modules(self):
        self.metrics_vertical_toggle_revealer.set_reveal_child(True)
        self.systray_revealer.set_reveal_child(True)
