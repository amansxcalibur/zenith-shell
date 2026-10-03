from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from widgets.elastic.elastic_stack import ElasticStack

from config.info import IS_WAYLAND

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window

from modules.notifications.notification import NotificationManager
from utils.helpers import get_absolute_wayland_widget_position

import icons
from config.config import config
from config.info import SHELL_NAME, IS_WAYLAND


class TopPill(Window, Service):
    WIN_ROLE = f"{SHELL_NAME}-top-pill"

    @Signal
    def on_drag(self, drag_state: object, new_x: int, new_y: int): ...

    @Signal
    def on_drag_end(self, drag_state: object): ...

    @Signal
    def child_changed(self, child_controls: object): ...

    def __init__(self, **kwargs):
        pill_config_node = config.get_node("top_pill")

        if IS_WAYLAND:
            super().__init__(
                layer="overlay",
                keyboard_mode="on-demand",
                anchor=f"{pill_config_node.get('POSITION.y')} {pill_config_node.get('POSITION.x')}",
                exclusivity="none",
                margin=(0, 0, 0, 0),
                visible=True,
                all_visible=True,
            )
        else:
            super().__init__(
                name="pill",
                layer="top",
                geometry="top",
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
        self._pos = pill_config_node.get("POSITION")
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

        self.stack = ElasticStack(
            name="top-pill-stack",
            transition_type="crossfade",
            transition_duration=250,
            interpolate_size=True,
            children=[
                self.pill_compact,
                self.notification,
            ],
        )
        self.stack.get_inner_stack().set_homogeneous(False)

        self.pill_container = ClippingBox(
            name="top-pill-container", orientation="v", children=[self.stack]
        )
        self.children = self.pill_container

        self.pill_close_btn = Button(
            child=MaterialIconLabel(
                name="close-control-label", icon_text=icons.close.symbol()
            ),
            tooltip_text="Close",
            on_clicked=lambda *_: self.close(),
        )

        self.add_keybinding("Escape", lambda *_: self.close())

        # drag events
        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

        self.connect("delete-event", self.on_delete_event)

    def focus_pill(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            return
        exec_shell_command_async(f'i3-msg [window_role="^{self.WIN_ROLE}$"] focus')

    def unfocus_pill(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            return
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
                focus_callback=self.notification_manager.open_notification_stack,
            )
        else:
            self._close_view(
                unfocus_callback=self.notification_manager.close_notification_stack
            )

    def open(self):
        # opens notifications
        self._open_view(
            self.notification,
            focus_callback=self.notification_manager.open_notification_stack,
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
        if event.button != 1:  # not left mouse button
            return

        self._drag_state["dragging"] = True
        # self._drag_state["last_x"] = event.x_root
        # self._drag_state["last_y"] = event.y_root

        x, y = self.get_current_position()

        if IS_WAYLAND:
            self._old_anchors = {
                edge: GtkLayerShell.get_anchor(self, edge)
                for edge in (
                    GtkLayerShell.Edge.TOP,
                    GtkLayerShell.Edge.BOTTOM,
                    GtkLayerShell.Edge.LEFT,
                    GtkLayerShell.Edge.RIGHT,
                )
            }
            self._old_margins = {
                edge: GtkLayerShell.get_margin(self, edge) for edge in self._old_anchors
            }

            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, False)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, False)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)

            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, y)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, x)

        self._drag_state["offset_x"] = event.x_root - x
        self._drag_state["offset_y"] = event.y_root - y
        self._drag_state["start_pos"] = (x, y)

    def on_motion(self, widget, event):
        if not self._drag_state["dragging"]:
            return

        new_x = int(event.x_root - self._drag_state["offset_x"])
        new_y = int(event.y_root - self._drag_state["offset_y"])

        # self._drag_state["last_x"] = event.x_root
        # self._drag_state["last_y"] = event.y_root

        self.set_current_position(new_x, new_y)
        self.on_drag(self._drag_state, new_x, new_y)  # always absolute now

    def on_button_release(self, widget, event):
        if event.button != 1 or not self._drag_state["dragging"]:
            return

        self._drag_state["dragging"] = False
        self.on_drag_end(self._drag_state)

    def get_current_position(self):
        # top left coordinates
        if not IS_WAYLAND:
            return self.get_position()
        success, x, y = get_absolute_wayland_widget_position(self)
        return (x, y) if success else (0, 0)

    def set_current_position(self, x, y):
        if IS_WAYLAND:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, int(x))
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, int(y))
        else:
            self.move(int(x), int(y))

    def get_position_config(self) -> dict:
        return config.get("top_pill.POSITION")

    def set_position_config(self, x: str, y: str):
        self._pos["x"] = x
        self._pos["y"] = y
        config.set("top_pill.POSITION", {"x": x, "y": y})
        self.update_controls_positions()

    def get_drag_state(self):
        return self._drag_state

    def update_controls_positions(self):
        self.open()

    def on_delete_event(self, *_):
        # don't close me :(
        return True
