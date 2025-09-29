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
from modules.power_menu import PowerMenu

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
        
        self.player = PlayerContainer(window = self)
        self.player.add_style_class("hide-player")

        self.active_window = ActiveWindow()
        self.user = Label(
            label="aman@brewery" if not info.VERTICAL else "am\nan\n@\nbr\new\ner\ny",
            name="user-label",
        )
        # self.dot_placeholder = Label(label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", name="collapsed-bar")
        self.dot_placeholder = Box(style="min-width:1px; min-height:1px;")
        self.user.add_style_class('hide')
        self.active_window.active_window.add_style_class('hide')
        self.pill_compact = Stack(
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
        self.pill_compact.set_visible_child(self.dot_placeholder)



        self.launcher = AppLauncher(notch=self)
        # self.launcher = Box()
        self.launcher.add_style_class("launcher-contract-init")
        self.wallpaper = WallpaperSelector(notch=self)
        self.wallpaper.add_style_class("wallpaper-contract")
        self.text = Label(label="hele", name="text")
        self.controls = ControlsManager()
        self.dashboard = Dashboard(controls=self.controls)
        self.dashboard.add_style_class("hide")
        self.power_menu = PowerMenu()
        self.power_menu.add_style_class("hide-menu")

        self.stack = Stack(
            name="pill-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[
                self.pill_compact,
                # self.user,
                self.launcher,
                self.wallpaper,
                self.player,
                self.dashboard,
                self.power_menu
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
        exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")
        self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
        if self.stack.get_visible_child() == self.pill_compact:
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

        elif self.stack.get_visible_child() == self.power_menu:
            toggle_class(self.power_menu, 'reveal-menu', 'hide-menu')
            self.launcher.remove_style_class("launcher-contract-init")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.launcher)

            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

    def close(self, *_):
        self.unfocus_notch()
        if self.stack.get_visible_child() != self.pill_compact:
            exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.close()'")
        
        if self.stack.get_visible_child() == self.player:
            self.player.unregister_keybindings()
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            else:
                self.player.add_style_class("hide-player")

            self.stack.set_visible_child(self.pill_compact)

        if self.stack.get_visible_child() == self.power_menu:
            toggle_class(self.power_menu, 'reveal-menu', 'hide-menu')
            self.stack.set_visible_child(self.pill_compact)

        elif self.stack.get_visible_child() != self.pill_compact:
            self.stack.remove_style_class("expander")
            exec_shell_command_async(
                f" fabric-cli exec {info.SHELL_NAME} 'dockBar.reveal_overlapping_modules()'"
            )

            toggle_class(self.dashboard, "reveal", "hide")
            self.wallpaper.remove_style_class("wallpaper-expand")
            self.wallpaper.add_style_class("wallpaper-contract")

            self.stack.add_style_class("contracter")

            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.pill_compact)
            # self.launcher.close_launcher()

        # for cases where player->dmenu->close()
        if info.VERTICAL:
            self.player.add_style_class("vertical")
        else:
            self.player.add_style_class("hide-player")

        # self.stack.add_style_class("hide")

        if self.stack.get_visible_child() != self.pill_compact:
            self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
        self.show_all()

    def toggle_player(self, *_):
        if self.stack.get_visible_child() != self.player:
            self.focus_notch()
            self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")
            toggle_class(self.player, "hide-player", "reveal-player")
            # launcher->player
            toggle_class(self.launcher, "launcher-expand", "launcher-contract")
            # wallpaper->player
            if self.stack.get_visible_child() == self.launcher:
                toggle_class(self.wallpaper, "wallpaper-expand", "wallpaper-contract")
            # dashboard->player
            toggle_class(self.dashboard, "reveal", "hide")
            # power menu->player
            toggle_class(self.power_menu, 'reveal-menu', 'hide-menu')

            self.stack.add_style_class("contracter")
            self.stack.set_visible_child(self.player)
            self.player.register_keybindings()
        else:
            self.player.unregister_keybindings()
            exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.close()'")
            self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            toggle_class(self.player, "reveal-player", "hide-player")
            self.stack.set_visible_child(self.pill_compact)
            self.unfocus_notch()

    def toggle_power_menu(self, *_):
        if self.stack.get_visible_child() != self.power_menu:
            self.focus_notch()
            self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")
            # launcher->menu
            toggle_class(self.launcher, "launcher-expand", "launcher-contract")
            # player->menu
            toggle_class(self.player, "reveal-player", "hide-player")
            # wallpaper->menu
            if self.stack.get_visible_child() == self.launcher:
                toggle_class(self.wallpaper, "wallpaper-expand", "wallpaper-contract")
            # dashboard->menu
            toggle_class(self.dashboard, "reveal", "hide")
            toggle_class(self.power_menu, 'hide-menu', 'reveal-menu')
            self.stack.set_visible_child(self.power_menu)
        else:
            self.unfocus_notch()
            self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
            exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.close()'")
            toggle_class(self.power_menu, 'reveal-menu', 'hide-menu')
            self.stack.set_visible_child(self.pill_compact)

    def open_notch(self, mode):
        match mode:
            case "wallpapers":
                exec_shell_command_async(
                    f" fabric-cli exec {info.SHELL_NAME} 'dockBar.hide_overlapping_modules()'"
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

    def cycle_modes(self, *_):
        if self.stack.get_visible_child() == self.pill_compact:
            if self.pill_compact.get_visible_child() == self.user:
                toggle_class(self.user, "hide", "reveal")
                toggle_class(self.active_window.active_window, "hide", "reveal")
                self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
                exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")
                self.pill_compact.set_visible_child(self.active_window.active_window)
            elif self.pill_compact.get_visible_child() == self.active_window.active_window:
                toggle_class(self.active_window.active_window, "reveal", "hide")
                toggle_class(self.user, "reveal", "hide")
                exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.close()'")
                self.lift_box.set_style("min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
                self.pill_compact.set_visible_child(self.dot_placeholder)
            else:
                toggle_class(self.active_window.active_window, "reveal", "hide")
                toggle_class(self.user, "hide", "reveal")
                self.lift_box.set_style("min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)")
                exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")
                self.pill_compact.set_visible_child(self.user)
        else:
            return
