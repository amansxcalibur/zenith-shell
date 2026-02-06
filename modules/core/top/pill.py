from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from widgets.material_label import MaterialIconLabel
from widgets.overrides import PatchedX11Window as Window

from modules.notification import NotificationManager

import icons
from config.info import config, SHELL_NAME


class TopPill(Window, Service):
    WIN_ROLE = "top-pill"

    @Signal
    def on_drag(self, drag_state: object, new_x: int, new_y: int): ...

    @Signal
    def on_drag_end(self, drag_state: object): ...

    @Signal
    def child_changed(self, child_controls: object): ...

    def __init__(self, **kwargs):
        super().__init__(
            name="pill",
            layer="top",
            geometry="bottom",
            type_hint="normal",
            margin=(0, 0, 0, 0),
            visible=True,
            all_visible=True,
        )
        self.set_role(self.WIN_ROLE)

        self._drag_state = {
            "dragging": False,
            "offset_x": 0,
            "offset_y": 0,
            "start_pos": None,
        }
        self._current_compact_mode = None
        self._dock_is_visible = True
        # for custom geometry handle in ShellWindowManager
        self._pos = config.top_pill.POSITION  # changes the config
        self.is_lift_enable = False

        self.notification_manager = NotificationManager()
        self.notification = self.notification_manager.get_notifications_box()
        self.active_notifications = (
            self.notification_manager.get_active_notifications_box()
        )

        # pill-compact
        self.dot_placeholder = Box(style="min-width:1px; min-height:1px;")
        self.pill_compact = Stack(
            name="collapsed",
            transition_type="crossfade",
            transition_duration=250,
            style_classes="" if not config.VERTICAL else "vertical",
            children=(
                [
                    self.active_notifications,
                ]
            ),
        )
        self.pill_compact.set_visible_child(self.dot_placeholder)
        self._current_compact_mode = self.dot_placeholder
        self.pill_compact.set_interpolate_size(True)
        self.pill_compact.set_homogeneous(False)

        self.lift_box = Box(style="min-height:0px;")  # 40-3-1 -3(dock padding)

        self.stack = Stack(
            name="top-pill-stack",
            transition_type="crossfade",
            transition_duration=250,
            children=[
                self.pill_compact,
                self.notification,
            ],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.pill_container = Box(
            name="top-pill-container", orientation="v", children=[self.stack]
        )
        self.children = self.pill_container

        self.pill_close_btn = Button(
            child=MaterialIconLabel(name="close-control-label", icon_text=icons.close.symbol()),
            tooltip_text="Close",
            on_clicked=lambda *_: self.close(),
        )

        self.add_keybinding("Escape", lambda *_: self.close())

        # drag events
        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

    def focus_pill(self):
        exec_shell_command_async(f'i3-msg [window_role="^{self.WIN_ROLE}$"] focus')

    def unfocus_pill(self):
        exec_shell_command_async("i3-msg focus mode_toggle")

    def lift_pill(self):
        if not self.is_lift_enable:
            return
        if self._dock_is_visible and (
            (self._pos["x"], self._pos["y"]) == ("center", "top")
        ):
            self.lift_box.set_style(
                "min-height:36px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            )

    def lower_pill(self):
        self.lift_box.set_style(
            "min-height:0px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
        )

    def open_dock(self):
        exec_shell_command_async(f" fabric-cli exec {SHELL_NAME} 'top_bar.open()'")

    def close_dock(self):
        exec_shell_command_async(f"fabric-cli exec {SHELL_NAME} 'top_bar.close()'")

    def toggle_notification(self):
        if self.stack.get_visible_child() != self.notification:
            self._open_view(
                self.notification,
                focus_callback=self.notification_manager.open_notification_stack(),
            )
        else:
            self._close_view(
                unfocus_callback=self.notification_manager.close_notification_stack()
            )

    def open(self):
        # opens notifications
        self._open_view(
            self.notification,
            lambda: (self.notification_manager.open_notification_stack(),),
        )

    def close(self, *_):
        self._close_view()

    def _open_view(self, view, focus_callback=None):
        # unregister current view's keybindings
        curr_child = self.stack.get_visible_child()
        if hasattr(curr_child, "unregister_keybindings"):
            curr_child.unregister_keybindings()

        self.focus_pill()
        self.lower_pill()
        self.open_dock()

        self.stack.set_visible_child(view)

        controls = []

        if hasattr(view, "register_keybindings"):
            view.register_keybindings()

        if hasattr(view, "get_controls"):
            controls = view.get_controls()

        controls.append(self.pill_close_btn)

        self.child_changed(controls)

        if focus_callback:
            focus_callback()

    def _close_view(self, unfocus_callback=None):
        # unregister current view's keybindings
        curr_child = self.stack.get_visible_child()
        if hasattr(curr_child, "unregister_keybindings"):
            curr_child.unregister_keybindings()

        if unfocus_callback:
            unfocus_callback()

        if self._current_compact_mode == self.dot_placeholder:
            self.close_dock()
            self.lift_pill()

        self.unfocus_pill()
        self.stack.set_visible_child(self.pill_compact)
        self.child_changed([])
        self.show_all()

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

    def update_controls_positions(self):
        self.open()
