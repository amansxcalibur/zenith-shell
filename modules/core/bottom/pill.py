from typing import TYPE_CHECKING

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from config.config import config
from config.info import USERNAME, HOSTNAME, IS_WAYLAND, IPC_UTIL

from modules.dashboard import Dashboard
from modules.power_menu import PowerMenu
from modules.player import PlayerContainer
from modules.controls import ControlsManager
from modules.clipboard import ClipboardHistory
from modules.wallpaper import WallpaperSelector
from modules.launcher import AppLauncher, AppCommands
from modules.workspaces.workspaces import ActiveWindow
from modules.core.bottom.dock.placement import (
    DOCK_EDGE_BAND,
    DOCK_THICKNESS,
    PILL_HOLE_EXTRA,
    current_placement,
)

from services.power_profiles import power_profiles_service

from utils.colors import bind_theme
from utils.helpers import open_settings, get_absolute_wayland_widget_position

from widgets.clipping_box import BorderedClippingBox, ClippingBox
from widgets.elastic.elastic_stack import ElasticStack


import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib  # type: ignore

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window
    from widgets.anchor_canvas import AnchorCanvas

if TYPE_CHECKING:
    from .dock.bar import DockBar


class Pill(Window, Service):
    WIN_ROLE = "bottom-pill"
    LIFTED_HEIGHT = DOCK_THICKNESS - 4  # the compact pill overlaps the dock by 4px

    @Signal
    def on_drag(self, drag_state: object, new_x: int, new_y: int): ...

    @Signal
    def on_drag_end(self, drag_state: object): ...

    def __init__(self, **kwargs):
        pill_config = config.get_node("pill")
        if IS_WAYLAND:
            super().__init__(
                # name="pill",
                layer="top",
                keyboard_mode="none",
                anchor=f"{pill_config.get('POSITION.y')} {pill_config.get('POSITION.x')}",
                exclusivity="none",
                margin=(0, 0, 0, 0),
                visible=True,
                all_visible=True,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)
        else:
            super().__init__(
                name="pill",
                layer="top",
                geometry="bottom",
                type_hint="normal",
                margin=(0, 0, 0, 0),
                visible=True,
                all_visible=True,
            )
        if not IS_WAYLAND:
            self.set_role(self.WIN_ROLE)

        bind_theme(self)

        self._current_compact_mode = None
        self._dock_is_visible = True
        # set by the dock window itself; called directly, not through
        # `fabric-cli exec` (a subprocess + D-Bus round trip back into us)
        self.dock_bar: DockBar | None = None
        # for custom geometry handle in ShellWindowManager
        self._pos = pill_config.get("POSITION")  # changes the config
        self._drag_state = {
            "dragging": False,
            "offset_x": 0,
            "offset_y": 0,
            "start_pos": None,
            "last_x": 0,
            "last_y": 0,
        }
        self._animations_enabled = (
            True
            if IS_WAYLAND
            else (power_profiles_service.active_profile != "power-saver")
        )

        # pill-compact
        self.active_window = ActiveWindow()
        self.user = Label(name="user-label", label=f"{USERNAME}@{HOSTNAME}")
        self.dot_placeholder = Box(style="min-width:1px; min-height:1px;")
        self.pill_compact = Stack(
            name="collapsed",
            transition_type="crossfade",
            transition_duration=250,
            style_classes="" if not config.VERTICAL else "vertical",
            children=[
                self.user,
                self.active_window.active_window,
                self.dot_placeholder,
            ],
        )
        self.pill_compact.set_visible_child(self.dot_placeholder)
        self._current_compact_mode = self.dot_placeholder
        self.pill_compact.set_interpolate_size(True)
        self.pill_compact.set_homogeneous(False)

        self.power_menu = PowerMenu()
        self.controls = ControlsManager()
        self.launcher = AppLauncher(window=self)
        self.player = PlayerContainer(window=self)
        self.wallpaper = WallpaperSelector(window=self)
        self.dashboard = Dashboard(controls=self.controls)
        self.clipboard = ClipboardHistory(window=self)

        # lifts the compact pill out of the dock it sits in
        self._seated_in_dock = current_placement().seats_pill
        self.lift_box = Box(
            style=f"min-height:{self.LIFTED_HEIGHT if self._seated_in_dock else 0}px;"
        )

        self.stack = ElasticStack(
            name="pill-stack",
            transition_type="crossfade",
            transition_duration=150,
            interpolate_size=True,
            bounce=self._animations_enabled,
            children=[
                self.pill_compact,
                self.launcher,
                self.wallpaper,
                self.player,
                self.dashboard,
                self.power_menu,
                self.clipboard,
            ],
        )
        self.stack.get_inner_stack().set_homogeneous(False)

        clipper = BorderedClippingBox if config.get("bar.BORDER") else ClippingBox
        self.pill_container = Box(
            name="pill-container",
            orientation="v",
            children=[
                clipper(name="pill-border-clipper", children=self.stack),
                self.lift_box,
            ],
        )
        self.canvas: AnchorCanvas | None = None
        if IS_WAYLAND:
            self.children = self.pill_container
        else:
            # the window covers the monitor and never resizes; the pill moves
            # and resizes inside it (see AnchorCanvas)
            geo = Gdk.Display.get_default().get_primary_monitor().get_geometry()
            self._canvas_origin = (geo.x, geo.y)
            self.canvas = AnchorCanvas(self.pill_container, geo.width, geo.height)
            self.children = self.canvas
            self.move(geo.x, geo.y)
            # mapping resets the input shape to the whole window
            self.connect_after(
                "map-event", lambda *_: self.canvas.reapply_input_shape()
            )

        self.add_keybinding("Escape", lambda *_: self.close())

        # drag events
        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

        power_profiles_service.connect("changed", self._on_power_profile_changed)
        self.connect("delete-event", self.on_delete_event)

        if IS_WAYLAND:
            self.stack.get_inner_stack().connect(
                "notify::transition-running", self._on_transition_done
            )

    def _on_transition_done(self, stack: Stack, pspec):
        if stack.get_transition_running():
            return
        child = stack.get_visible_child()
        match child:
            case self.launcher:
                entry = getattr(child, "search_entry", None)
                if entry and not entry.has_focus():
                    GLib.idle_add(entry.grab_focus)

            case self.wallpaper:
                GLib.idle_add(self.wallpaper.focus_search)

            case self.clipboard:
                GLib.idle_add(self.clipboard.focus_search)

    def _on_power_profile_changed(self, *_):
        if not IS_WAYLAND:
            self._animations_enabled = (
                power_profiles_service.active_profile != "power-saver"
            )
            self.stack.set_bounce(self._animations_enabled)

    def focus_pill(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            return
        exec_shell_command_async(f'{IPC_UTIL} [window_role="^{self.WIN_ROLE}$"] focus')

    def unfocus_pill(self):
        if IS_WAYLAND:
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            return
        exec_shell_command_async(f"{IPC_UTIL} focus mode_toggle")

    def _is_over_dock(self) -> bool:
        return (
            self._seated_in_dock
            and self._dock_is_visible
            and (self._pos["x"], self._pos["y"]) == ("center", "bottom")
        )

    def _set_lift(self, height: int):
        self.lift_box.set_style(
            f"min-height:{height}px; transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
        )

    def lift_pill(self):
        if self._is_over_dock():
            self._set_lift(self.LIFTED_HEIGHT)

    def lower_pill(self):
        # above the hole's floor by the same gap as its walls
        self._set_lift(DOCK_EDGE_BAND + PILL_HOLE_EXTRA if self._is_over_dock() else 0)

    def open_dock(self):
        if self.dock_bar is not None:
            GLib.idle_add(self._run_dock, self.dock_bar.open)

    def close_dock(self):
        if self.dock_bar is not None:
            GLib.idle_add(self._run_dock, self.dock_bar.close)

    @staticmethod
    def _run_dock(fn):
        fn()
        return False

    def open(self):
        # opens launcher
        self._open_view(
            self.launcher,
            lambda: (
                # self.launcher.open_launcher(),
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
            case AppCommands.WALLPAPERS:
                self.stack.set_visible_child(self.wallpaper)
                # Gtk.Stack moves focus into the new child itself (first
                # focusable widget) when the old child had it; take it back
                self.wallpaper.focus_search()
            case AppCommands.CLIPBOARD:
                self.stack.set_visible_child(self.clipboard)
                # after the switch: Gtk.Stack moves focus into the new child
                self.clipboard.open()
            case AppCommands.DASHBOARD:
                self.stack.set_visible_child(self.dashboard)
            case AppCommands.POWER:
                self.toggle_power_menu()
            case AppCommands.PLAYER:
                self.toggle_player()
            case AppCommands.SETTINGS:
                open_settings()
                self._close_view()

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
            self.enable_absolute_positioning(x, y)

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

    def enable_absolute_positioning(self, x: int | None = None, y: int | None = None):
        if not IS_WAYLAND:
            return

        if x is None or y is None:
            x, y = self.get_current_position()

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

    def apply_snap_anchors(
        self, enable_edges, disable_edges, bottom_margin=0, right_margin=0
    ):
        if not IS_WAYLAND:
            return

        for anchor in disable_edges:
            GtkLayerShell.set_anchor(self, anchor, False)
        for anchor in enable_edges:
            GtkLayerShell.set_anchor(self, anchor, True)

        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, bottom_margin)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, right_margin)

    def get_current_position(self) -> tuple[int, int]:
        # top left coordinates of the pill itself
        if self.canvas is not None:
            x, y = self.canvas.get_child_position()
            return x + self._canvas_origin[0], y + self._canvas_origin[1]
        success, x, y = get_absolute_wayland_widget_position(self)
        return (x, y) if success else (0, 0)

    def set_current_position(self, x, y):
        if self.canvas is not None:
            self.canvas.move_child(
                int(x) - self._canvas_origin[0], int(y) - self._canvas_origin[1]
            )
        elif IS_WAYLAND:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, int(x))
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, int(y))

    def get_pill_size(self) -> tuple[int, int]:
        if self.canvas is not None and (rect := self.canvas.child_rect):
            return rect[2], rect[3]
        if self.canvas is not None:
            _, nat = self.pill_container.get_preferred_size()
            return nat.width, nat.height
        return self.get_size()

    def to_canvas(self, x: int, y: int) -> tuple[int, int]:
        """Root coordinates to the canvas's own (X11 only)."""
        return x - self._canvas_origin[0], y - self._canvas_origin[1]

    def get_position_config(self) -> dict:
        return config.get("pill.POSITION")

    def set_position_config(self, x: str, y: str):
        self._pos["x"] = x
        self._pos["y"] = y
        config.set("pill.POSITION", {"x": x, "y": y})

    def get_drag_state(self):
        return self._drag_state

    def on_delete_event(self, *_):
        # don't close me :(
        return True
