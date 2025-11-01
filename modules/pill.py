from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.x11 import X11Window as Window
from fabric.utils.helpers import exec_shell_command_async

from modules.dashboard import Dashboard
from modules.launcher import AppLauncher
from modules.power_menu import PowerMenu
from modules.player import PlayerContainer
from modules.workspaces import ActiveWindow
from modules.controls import ControlsManager
from modules.wallpaper import WallpaperSelector

import config.info as info


class Pill(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="pill",
            layer="top",
            geometry="bottom" if not info.VERTICAL else "left",
            type_hint="normal",
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self._current_compact_mode = None
        self._dock_is_visible = True

        # pill-compact
        self.active_window = ActiveWindow()
        self.user = Label(name="user-label", label="aman@brewery")
        self.dot_placeholder = Box(style="min-width:1px; min-height:1px;")
        self.user.add_style_class("hide")
        self.active_window.active_window.add_style_class("hide")
        self.pill_compact = Stack(
            name="collapsed",
            transition_type="crossfade",
            transition_duration=250,
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
        self._current_compact_mode = self.dot_placeholder
        self.pill_compact.set_interpolate_size(True)
        self.pill_compact.set_homogeneous(False)

        self.power_menu = PowerMenu()
        self.controls = ControlsManager()
        self.launcher = AppLauncher(pill=self)
        self.player = PlayerContainer(window=self)
        self.wallpaper = WallpaperSelector(pill=self)
        self.dashboard = Dashboard(controls=self.controls)

        self.lift_box = Box(style="min-height:36px;")  # 40-3-1

        self.stack = Stack(
            name="pill-stack",
            transition_type="crossfade",
            transition_duration=250,
            children=[
                self.pill_compact,
                self.launcher,
                self.wallpaper,
                self.player,
                self.dashboard,
                self.power_menu,
            ],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.pill_container = Box(
            name="pill-container", orientation="v", children=[self.stack, self.lift_box]
        )
        self.children = self.pill_container

        self.add_keybinding("Escape", lambda *_: self.close())

    def focus_pill(self):
        exec_shell_command_async('i3-msg [window_role="pill"] focus')

    def unfocus_pill(self):
        exec_shell_command_async(f"i3-msg focus mode_toggle")

    def lift_pill(self):
        if self._dock_is_visible:
            self.lift_box.set_style(
                "min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            )

    def lower_pill(self):
        self.lift_box.set_style(
            "min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
        )

    def open_dock(self):
        exec_shell_command_async(f" fabric-cli exec {info.SHELL_NAME} 'dockBar.open()'")

    def close_dock(self):
        exec_shell_command_async(f"fabric-cli exec {info.SHELL_NAME} 'dockBar.close()'")

    def open(self):
        # opens launcher
        self._open_view(
            self.launcher,
            lambda: (
                self.launcher.open_launcher(),
                self.launcher.search_entry.set_text(""),
                self.launcher.search_entry.grab_focus(),
            ),
        )

    def close(self, *_):
        self._close_view()

    def _open_view(self, view, focus_callback=None):
        current = self.stack.get_visible_child()
        if current == self.player:
            self.player.unregister_keybindings()

        self.focus_pill()
        self.lower_pill()
        self.open_dock()
        self.stack.set_visible_child(view)

        if focus_callback:
            focus_callback()

    def _close_view(self):
        current = self.stack.get_visible_child()
        if current == self.player:
            self.player.unregister_keybindings()

        if self._current_compact_mode == self.dot_placeholder:
            self.close_dock()
            self.lift_pill()

        self.unfocus_pill()
        self.stack.set_visible_child(self.pill_compact)
        self.show_all()

    def toggle_player(self, *_):
        if self.stack.get_visible_child() != self.player:
            self._open_view(self.player, self.player.register_keybindings)
        else:
            self._close_view()

    def toggle_power_menu(self, *_):
        if self.stack.get_visible_child() != self.power_menu:
            self._open_view(self.power_menu, self.power_menu.btn_lock.grab_focus)
        else:
            self._close_view()

    def open_pill(self, mode):
        # called from the launcher
        match mode:
            case "wallpapers":
                self.stack.set_visible_child(self.wallpaper)
            case "dashboard":
                self.stack.set_visible_child(self.dashboard)

    def cycle_modes(self, forward=True):
        _modes = self.pill_compact.get_children()
        if not _modes:
            return

        _current_mode = self.pill_compact.get_visible_child()
        _current_index = _modes.index(_current_mode)

        next_index = (_current_index + (1 if forward else -1)) % len(_modes)
        _next_mode = _modes[next_index]
        if _next_mode == self.dot_placeholder:
            self.lift_pill()
            self.close_dock()
        else:
            self.lower_pill()
            self.open_dock()
        self.pill_compact.set_visible_child(_next_mode)
        self.stack.set_visible_child(self.pill_compact)
        self._current_compact_mode = _next_mode
