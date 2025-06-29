import fabric
from fabric import Application
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.datetime import DateTime
from fabric.widgets.revealer import Revealer
from fabric.widgets.x11 import X11Window as Window
from fabric.utils import get_relative_path
from fabric.utils.helpers import exec_shell_command_async
from i3ipc import Connection

from launcher import AppLauncher
from corner import Corners, MyCorner
from systray import SystemTray
from workspaces import Workspaces, ActiveWindow
from metrics import MetricsSmall, Battery
from player import PlayerContainer
from notification import Notification
import info
import icons.icons as icons
from dashboard import Dashboard

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk
from wallpaper import WallpaperSelector
from volume import VolumeSlider, VolumeSmall
from brightness import BrightnessSlider, BrightnessSmall
from controls import ControlsManager
from utilities.cursor import add_hover_cursor

import os, subprocess


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

    def toggle_vertical(self):
        CONFIG_PATH = os.path.expanduser("~/fabric/info.py")
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.strip().startswith("VERTICAL"):
                current_value = "True" in line
                new_value = "False" if current_value else "True"
                new_lines.append(f"VERTICAL = {new_value}\n")
            else:
                new_lines.append(line)

        with open(CONFIG_PATH, "w") as f:
            f.writelines(new_lines)

        # restart bar
        subprocess.run([f"{info.HOME_DIR}/i3scripts/flaunch.sh"])


class Notch(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notch",
            layer="top",
            geometry="top" if not info.VERTICAL else "left",
            # keyboard_mode="auto",
            type_hint="normal",
            # focusable=False
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self.launcher = AppLauncher(notch=self)

        self.controls = ControlsManager(notch=self)
        self.notification_revealer = None
        if not info.VERTICAL:
            self.vol_small = self.controls.get_volume_small()
            self.brightness_small = self.controls.get_brightness_small()
            self.launcher.launcher_box.remove_style_class("vertical")
            self.notification_revealer = Notification()
        self.volume_revealer = self.controls.get_volume_revealer()
        self.volume_overflow_revealer = self.controls.get_volume_overflow_revealer()
        self.brightness_revealer = self.controls.get_brightness_revealer()

        self.switch = True
        self.wallpapers = WallpaperSelector(notch=self)

        self.player = PlayerContainer()
        self.player.add_style_class("hide-player")

        self.active_window = ActiveWindow()
        if info.VERTICAL:
            self.workspaces = Workspaces()
        self.active_window.active_window.add_style_class("hide")
        self.user = Label(
            label="aman@brewery" if not info.VERTICAL else "am\nan\n@\nbr\new\ner\ny",
            name="user-label",
        )
        self.dot_placeholder = (
            Label(
                label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .",
                name="collapsed-bar",
            )
            if not info.VERTICAL
            else Label(label="~", name="collapsed-bar", style_classes="vertical")
        )

        self.notch_compact = Stack(
            name="collapsed",
            transition_type="crossfade",
            transition_duration=100,
            style_classes="" if not info.VERTICAL else "vertical",
            children=(
                [
                    self.user,
                    self.active_window.active_window,
                    self.dot_placeholder,
                ]
                if not info.VERTICAL
                else [self.workspaces]
            ),
        )
        self.notch_compact.set_visible_child(self.dot_placeholder)

        # EventBox with click event for toggling visibility
        self.collapsed = Gtk.EventBox(name="notch-compact")
        self.collapsed.set_visible(True)
        self.collapsed.add(self.notch_compact)

        self.collapsed.connect("button-press-event", self.toggle_collapse_child)

        self.dashboard = Dashboard(controls=self.controls)

        self.expanding = self.launcher

        if info.VERTICAL:
            self.expanding.add_style_class("vertical")
            self.wallpapers.add_style_class("vertical")
            self.player.add_style_class("vertical")
            self.launcher.add_style_class("vertical")
        else:
            # all these modules have class vertical bind to it by default
            self.wallpapers.remove_style_class("vertical")
            self.wallpapers.header_box.remove_style_class("vertical")
            self.wallpapers.scrolled_window.add_style_class("horizontal")
            self.player.remove_style_class("vertical")
        self.dashboard.add_style_class("hide")
        self.launcher.add_style_class("launcher-contract-init")
        self.wallpapers.add_style_class("wallpaper-contract")

        self.stack = Stack(
            name="notch-content",
            h_expand=True,
            v_expand=True,
            transition_type="crossfade",
            transition_duration=250,
            style_classes="" if not info.VERTICAL else "vertical",
            children=[
                self.collapsed,
                self.expanding,
                self.wallpapers,
                self.player,
                self.dashboard,
            ],
        )

        self.stack.set_visible_child(self.collapsed)
        self.add_keybinding("Escape", lambda *_: self.close())

        self.full_notch = Box(
            orientation="v" if not info.VERTICAL else "h",
            children=[
                CenterBox(
                    orientation="h" if not info.VERTICAL else "v",
                    center_children=[
                        CenterBox(
                            label="L",
                            name="left",
                            h_align="start",
                            v_align="start",
                            style_classes="" if not info.VERTICAL else "verticals",
                            center_children=[
                                Box(
                                    name="left-dum",
                                    style_classes=(
                                        "" if not info.VERTICAL else "vertical"
                                    ),
                                    children=(
                                        [self.brightness_small]
                                        if not info.VERTICAL
                                        else []
                                    ),
                                    v_expand=False,
                                )
                            ],
                            v_expand=False,
                        ),
                        self.stack,
                        CenterBox(
                            label="R",
                            name="right",
                            h_align="start",
                            v_align="start",
                            style_classes="" if not info.VERTICAL else "verticals",
                            center_children=[
                                Box(
                                    name="right-dum",
                                    style_classes=(
                                        "" if not info.VERTICAL else "vertical"
                                    ),
                                    children=(
                                        [self.vol_small] if not info.VERTICAL else []
                                    ),
                                    v_expand=False,
                                )
                            ],
                            v_expand=False,
                        ),
                    ],
                ),
            ],
        )
        self.hidden_notch = Box(style="min-height:1px;")
        self.visibility_stack = Stack(
            transition_type="over-down",
            transition_duration=100,
            children=[self.full_notch, self.hidden_notch],
        )

        self.children = Box(
            orientation="v" if not info.VERTICAL else "h",
            children=(
                [
                    self.visibility_stack,
                    CenterBox(
                        orientation="v",
                        h_align="center",
                        center_children=[
                            self.notification_revealer,
                            self.volume_revealer,
                            self.volume_overflow_revealer,
                            self.brightness_revealer,
                        ],
                    ),
                ]
                if not info.VERTICAL
                else [
                    self.visibility_stack,
                    CenterBox(
                        orientation="h",
                        v_align="center",
                        center_children=[
                            self.volume_revealer,
                            self.volume_overflow_revealer,
                            self.brightness_revealer,
                        ],
                    ),
                ]
            ),
        )
        # self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        # self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    def toggle_collapse_child(self, *_):
        if self.notch_compact.get_visible_child() == self.user:
            self.active_window.active_window.remove_style_class("hide")
            self.notch_compact.set_visible_child(self.active_window.active_window)
        elif self.notch_compact.get_visible_child() == self.active_window.active_window:
            self.active_window.active_window.add_style_class("hide")
            self.notch_compact.set_visible_child(self.dot_placeholder)
        else:
            self.notch_compact.set_visible_child(self.user)

    def toggle_player(self, *_):
        if self.stack.get_visible_child() != self.player:
            # exec_shell_command_async('i3-msg [class="Negative_margin.py"] focus')
            exec_shell_command_async('i3-msg [window_role="notch"] focus')
            self.player.remove_style_class("hide-player")
            self.player.add_style_class("reveal-player")
            # launcher->player
            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            # wallpaper->player
            if self.stack.get_visible_child() == self.expanding:
                exec_shell_command_async(
                    " fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'"
                )
                self.wallpapers.remove_style_class("wallpaper-expand")
                self.wallpapers.add_style_class("wallpaper-contract")
            # dashboard->player
            self.dashboard.add_style_class("hide")

            self.stack.add_style_class("contract")
            self.stack.set_visible_child(self.player)
        else:
            self.player.remove_style_class("reveal-player")
            self.player.add_style_class("hide-player")
            self.stack.set_visible_child(self.collapsed)

    def toggle_utility(self, *_):
        print("utiluty")

    def open(self, *_):
        if self.visibility_stack.get_visible_child() == self.full_notch:
            # self.steal_input()
            exec_shell_command_async('i3-msg [window_role="notch"] focus')
            if self.stack.get_visible_child() == self.collapsed:
                # self.stack.remove_style_class("contract")
                # self.stack.add_style_class("expand")
                # # self.remove_style_class("wallpaper-init")
                # self.dashboard.remove_style_class("hide")
                self.launcher.remove_style_class("launcher-contract-init")
                self.launcher.remove_style_class("launcher-contract")
                self.launcher.add_style_class("launcher-expand")
                self.stack.set_visible_child(self.expanding)

                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()

            elif self.stack.get_visible_child() == self.player:
                self.dashboard.add_style_class("hide")
                self.player.remove_style_class("reveal-player")
                self.player.add_style_class("hide-player")
                self.launcher.remove_style_class("launcher-contract")
                self.launcher.add_style_class("launcher-expand")
                self.stack.set_visible_child(self.expanding)

                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()
        else:
            print("Notch is hidden")
        self.show_all()

    def close(self, *_):
        if self.stack.get_visible_child() == self.player:
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            self.player.add_style_class("hide-player")

            self.stack.set_visible_child(self.collapsed)

        elif self.stack.get_visible_child() != self.collapsed:
            self.stack.remove_style_class("expand")
            exec_shell_command_async(
                " fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'"
            )

            # self.unsteal_input()
            self.wallpapers.remove_style_class("wallpaper-expand")
            self.wallpapers.add_style_class("wallpaper-contract")
            self.dashboard.add_style_class("hide")

            self.stack.add_style_class("contract")

            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.collapsed)
            exec_shell_command_async(f"i3-msg focus mode_toggle")
            # self.launcher.close_launcher()

        # for cases where player->dmenu->close()
        if info.VERTICAL:
            self.player.add_style_class("vertical")
        else:
            self.player.add_style_class("hide-player")
        self.show_all()

    def open_notch(self, mode):
        match mode:
            case "wallpapers":
                exec_shell_command_async(
                    " fabric-cli exec bar-example 'dockBar.hide_overlapping_modules()'"
                )
                self.remove_style_class("launcher-contract")
                self.dashboard.add_style_class("hide")
                # if info.VERTICAL:
                # self.wallpapers.remove_style_class("vertical")
                # else:
                self.wallpapers.remove_style_class("wallpaper-contract")
                self.wallpapers.remove_style_class("wallpaper-init")
                self.wallpapers.add_style_class("wallpaper-expand")
                self.stack.set_visible_child(self.wallpapers)
            case "dashboard":
                self.dashboard.remove_style_class("hide")
                self.remove_style_class("launcher-contract")
                self.stack.set_visible_child(self.dashboard)


if __name__ == "__main__":
    notch = Notch()
    dockBar = DockBar()
    notch.set_role("notch")
    dockBar.notch = notch
    notification = None

    if info.VERTICAL:
        from notification import NotificationPopup

        notification = NotificationPopup()
        dockBar.set_title("fabric-dock")
        # make the window consume all vertical space
        monitor = dockBar._display.get_primary_monitor()
        rect = monitor.get_geometry()
        scale = monitor.get_scale_factor()
        dockBar.set_size_request(0, rect.height * scale)
        dockBar.show_all()
        notch.show_all()
        # bar.set_keep_above(True)

    app_kwargs = {
        "notch": notch,
        "dockBar": dockBar,
        "open_inspector": False,
    }

    if notification:
        app_kwargs["notification"] = notification

    app = Application("bar-example", **app_kwargs)

    def set_css():
        app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))

    app.set_css = set_css
    app.set_css()

    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()
