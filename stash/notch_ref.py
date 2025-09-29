import fabric
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.x11 import X11Window as Window
from fabric.utils.helpers import exec_shell_command_async

from modules.launcher import AppLauncher
from modules.controls import ControlsManager
from modules.dashboard import Dashboard
from modules.notifications import Notification
from modules.player import PlayerContainer
from modules.workspaces import Workspaces, ActiveWindow
from modules.wallpaper import WallpaperSelector
from utils.helpers import toggle_class

import config.info as info

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

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

    def focus_notch(self):
        exec_shell_command_async('i3-msg [window_role="notch"] focus')
    
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
            self.focus_notch()

            toggle_class(self.player, "hide-player", "reveal-player")
            # launcher->player
            toggle_class(self.launcher, "launcher-expand", "launcher-contract")
            # wallpaper->player
            if self.stack.get_visible_child() == self.expanding:
                exec_shell_command_async(
                    "fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'"
                )
                toggle_class(self.wallpapers, "wallpaper-expand", "wallpaper-contract")
            # dashboard->player
            self.dashboard.add_style_class("hide")

            self.stack.add_style_class("contract")
            self.stack.set_visible_child(self.player)
        else:
            toggle_class(self.player, "reveal-player", "hide-player")
            self.stack.set_visible_child(self.collapsed)

    def toggle_utility(self, *_):
        print("utiluty")

    def open(self, *_):
        if self.visibility_stack.get_visible_child() == self.full_notch:
            # self.steal_input()
            self.focus_notch()
            if self.stack.get_visible_child() == self.collapsed:
                # self.stack.remove_style_class("contract")
                # self.stack.add_style_class("expand")
                # # self.remove_style_class("wallpaper-init")
                # self.dashboard.remove_style_class("hide")
                self.launcher.remove_style_class("launcher-contract-init")
                toggle_class(self.launcher, "launcher-contract", "launcher-expand")
                self.stack.set_visible_child(self.expanding)

                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()

            elif self.stack.get_visible_child() == self.player:
                self.dashboard.add_style_class("hide")
                toggle_class(self.player, "reveal-player", "hide-player")
                toggle_class(self.launcher, "launcher-contract", "launcher-expand")
                self.stack.set_visible_child(self.expanding)

                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()
        else:
            print("Notch is hidden")
        self.show_all()

    def close(self, *_):
        if self.stack.get_visible_child() == self.player:
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            toggle_class(self.player, "reveal-player", "hide-player")

            self.stack.set_visible_child(self.collapsed)

        elif self.stack.get_visible_child() != self.collapsed:
            exec_shell_command_async(
                " fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'"
            )

            # self.unsteal_input()
            toggle_class(self.wallpapers, "wallpaper-expand", "wallpaper-contract")
            self.dashboard.add_style_class("hide")
            toggle_class(self.stack, "expand", "contract")
            toggle_class(self.launcher, "launcher-expand", "launcher-contract")

            self.stack.set_visible_child(self.collapsed)
            exec_shell_command_async(f"i3-msg focus mode_toggle")
            # self.launcher.close_launcher()

        # player->dmenu->close()
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

                self.wallpapers.remove_style_class("wallpaper-init")
                toggle_class(self.wallpapers, "wallpaper-contract", "wallpaper-expand")

                self.stack.set_visible_child(self.wallpapers)
            case "dashboard":
                self.dashboard.remove_style_class("hide")
                self.remove_style_class("launcher-contract")

                self.stack.set_visible_child(self.dashboard)
