from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.x11 import X11Window as Window
from fabric.utils.helpers import exec_shell_command_async
from modules.launcher import AppLauncher

from modules.workspaces import ActiveWindow
from modules.player import PlayerContainer
import config.info as info
from utils.helpers import toggle_class

from modules.wallpaper import WallpaperSelector
from modules.controls import ControlsManager
from modules.dashboard import Dashboard

class Notch(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notch",
            layer="top",
            geometry="bottom" if not info.VERTICAL else "left",
            type_hint="normal",
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self.bool = False
        self.active_window = ActiveWindow()
        self.player = PlayerContainer(window = self)
        self.player.add_style_class("hide-player")
        self.user = Label(
            label="aman@brewery" if not info.VERTICAL else "am\nan\n@\nbr\new\ner\ny",
            name="user-label",
        )
        # self.dot_placeholder = Label(label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", name="collapsed-bar")
        self.dot_placeholder = Box(style="min-width:1px; min-height:1px;")
        # self.dot_placeholder = Stack()
        self.launcher = AppLauncher(notch=self)
        self.launcher.add_style_class("launcher-contract-init")
        self.wallpaper = WallpaperSelector(notch=self)
        self.wallpaper.add_style_class("wallpaper-contract")
        self.text = Label(label="hele", name="text")
        self.controls = ControlsManager()
        self.dashboard = Dashboard(controls=self.controls)
        self.dashboard.add_style_class("hide")

        self.stack = Stack(
            name="pill-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[
                self.dot_placeholder,
                # self.user,
                self.launcher,
                self.wallpaper,
                self.player,
                self.dashboard,
            ],
        )

        self.lift_box = Box(style="min-height:36px;") # 40-3-1
        self.children = Box(
            orientation='v',
            children=[
                self.stack,
                self.lift_box
            ]
        )

        self.add_keybinding("Escape", lambda *_: self.close())

    def focus_notch(self):
        exec_shell_command_async('i3-msg [window_role="notch"] focus')
    
    def unfocus_notch(self):
        exec_shell_command_async(f"i3-msg focus mode_toggle")

    def open(self):
        self.focus_notch()
        exec_shell_command_async(" fabric-cli exec bar-example 'dockBar.open()'")
        self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
        if self.stack.get_visible_child() == self.dot_placeholder:
            # open launcher
            self.launcher.remove_style_class("launcher-contract-init")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.launcher)

            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

        elif self.stack.get_visible_child() == self.player:
            self.player.unregister_keybindings()
            toggle_class(self.player, "reveal-player", "hide-player")
            toggle_class(self.dashboard, "reveal", "hide")
            self.launcher.remove_style_class("launcher-contract-init")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.launcher)

            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

    def close(self, *_):
        self.unfocus_notch()
        exec_shell_command_async(" fabric-cli exec bar-example 'dockBar.close()'")
        if self.stack.get_visible_child() == self.player:
            self.player.unregister_keybindings()
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            else:
                self.player.add_style_class("hide-player")

            self.stack.set_visible_child(self.dot_placeholder)

        elif self.stack.get_visible_child() != self.dot_placeholder:
            self.stack.remove_style_class("expander")
            exec_shell_command_async(
                " fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'"
            )

            toggle_class(self.dashboard, "reveal", "hide")
            self.wallpaper.remove_style_class("wallpaper-expand")
            self.wallpaper.add_style_class("wallpaper-contract")

            self.stack.add_style_class("contracter")

            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.dot_placeholder)
            # self.launcher.close_launcher()

        # for cases where player->dmenu->close()
        if info.VERTICAL:
            self.player.add_style_class("vertical")
        else:
            self.player.add_style_class("hide-player")

        # self.stack.add_style_class("hide")

        self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
        self.show_all()

    def toggle_player(self, *_):
        if self.stack.get_visible_child() != self.player:
            self.focus_notch()
            self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            exec_shell_command_async(" fabric-cli exec bar-example 'dockBar.open()'")
            toggle_class(self.player, "hide-player", "reveal-player")
            # launcher->player
            toggle_class(self.launcher, "launcher-expand", "launcher-contract")
            # wallpaper->player
            if self.stack.get_visible_child() == self.launcher:
                toggle_class(self.wallpaper, "wallpaper-expand", "wallpaper-contract")
            # dashboard->player
            toggle_class(self.dashboard, "reveal", "hide")

            self.stack.add_style_class("contracter")
            self.stack.set_visible_child(self.player)
            self.player.register_keybindings()
        else:
            self.player.unregister_keybindings()
            exec_shell_command_async(" fabric-cli exec bar-example 'dockBar.close()'")
            self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            toggle_class(self.player, "reveal-player", "hide-player")
            self.stack.set_visible_child(self.dot_placeholder)
            self.unfocus_notch()

    def open_notch(self, mode):
        match mode:
            case "wallpapers":
                exec_shell_command_async(
                    " fabric-cli exec bar-example 'dockBar.hide_overlapping_modules()'"
                )
                self.remove_style_class("launcher-contract")
                self.dashboard.add_style_class("hide")

                self.wallpaper.remove_style_class("wallpaper-init")
                toggle_class(self.wallpaper, "wallpaper-contract", "wallpaper-expand")

                self.stack.set_visible_child(self.wallpaper)
            case "dashboard":
                toggle_class(self.dashboard, "hide", "reveal")
                self.remove_style_class("launcher-contract")

                self.stack.set_visible_child(self.dashboard)