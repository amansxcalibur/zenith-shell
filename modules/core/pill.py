from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.x11 import X11Window as Window
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from modules.dashboard import Dashboard
from modules.launcher import AppLauncher
from modules.power_menu import PowerMenu
from modules.player import PlayerContainer
from modules.workspaces import ActiveWindow
from modules.controls import ControlsManager
from modules.wallpaper import WallpaperSelector

import config.info as info


class Pill(Window, Service):

    @Signal
    def on_drag(self, drag_state: object, new_x: int, new_y: int): ...

    @Signal
    def on_drag_end(self, drag_state: object): ...

    def __init__(self, **kwargs):
        super().__init__(
            name="pill",
            layer="top",
            geometry="bottom",
            type_hint="normal",
            margin=(0,0,0,0),
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

        self._drag_state = {
            "dragging": False,
            "offset_x": 0,
            "offset_y": 0,
            "start_pos": None,
        }

        # drag events
        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

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

    def on_button_press(self, widget, event):
        if event.button == 1:  # Left mouse button
            self._drag_state["dragging"] = True
            win_x, win_y = self.get_position()
            self._drag_state["offset_x"] = event.x_root - win_x
            self._drag_state["offset_y"] = event.y_root - win_y
            self._drag_state["start_pos"] = (win_x, win_y)

    def on_motion(self, widget, event):
        if not self._drag_state["dragging"]:
            return

        new_x = int(event.x_root - self._drag_state["offset_x"])
        new_y = int(event.y_root - self._drag_state["offset_y"])

        self.on_drag(self._drag_state, new_x, new_y)
        self.move(new_x, new_y)

    def on_button_release(self, widget, event):
        if event.button != 1 or not self._drag_state["dragging"]:
            return

        self._drag_state["dragging"] = False
        self.on_drag_end(self._drag_state)

    def get_drag_state(self):
        return self._drag_state
