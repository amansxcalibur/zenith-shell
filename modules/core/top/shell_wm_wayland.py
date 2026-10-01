from __future__ import annotations

from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pill import TopPill
    from .bar import TopBar

from services.animator import Animator

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GtkLayerShell  # type: ignore


class ShellTopWindowManager:
    DOCK_HEIGHT = 43

    # -- Properties --
    @property
    def pill_widget(self):
        return self.pill

    @property
    def dock_widget(self):
        return self.top_bar

    def __init__(self, pill: TopPill, dockBar: TopBar):
        if not pill or not dockBar:
            raise ValueError(
                "ShellWindowManager requires both 'pill' and 'dockBar' instances."
            )

        self.pill = pill
        self.top_bar = dockBar
        self.is_dock_overflowing = False

        self.pill_start_x, self.pill_start_y = self.pill.get_current_position()
        self.pill_target_x = self.pill_start_x
        self.pill_target_y = self.pill_start_y

        self.animator = Animator(
            bezier_curve=(0.15, 0.88, 0.68, 0.95),
            duration=0.3,
            min_value=0,
            max_value=1,
            tick_widget=self.pill,
            notify_value=lambda p, *_: self._apply_position(p.value),
            on_finished=self._on_snap_finish,
        )

        self.pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        self._setup_size_groups()

        # Connect signals
        self.pill.connect("on-drag", self._set_dock_state)
        self.pill.connect("on-drag-end", lambda w, state: self._snap_pill())

        self._disconnect_geometry_enforcement(self.pill)

    def _setup_size_groups(self):
        self.pill_size_group.add_widget(self.top_bar.pill_dock)
        self.pill_size_group.add_widget(self.pill.pill_container)

    def _remove_size_groups(self):
        self.pill_size_group.remove_widget(self.pill.pill_container)

    def _get_monitor_geometry(self, widget):
        display = Gdk.Display.get_default()
        win = widget.get_window()
        if not win:
            return Gdk.Rectangle()
        monitor = display.get_monitor_at_window(win)
        return monitor.get_geometry()

    def _is_dock_visible(self):
        return self.top_bar.get_visible()

    def _on_dock_visibility_toggle(self, *args):
        self._snap_pill()

    def _set_dock_state(self, source, drag_state, x: int, y: int):
        pill_is_in_dock_zone = (y) < (self.DOCK_HEIGHT)
        # TopBar handles update-only-if-changed internally
        if pill_is_in_dock_zone:
            self.top_bar.override_reset()
        else:
            self.top_bar.override_close()

    def _snap_pill(self, animate: bool = True, fixed: bool = False):
        drag_state = self.pill.get_drag_state()
        if drag_state and drag_state.get("dragging"):
            return

        geo = self._get_monitor_geometry(self.pill)
        win_x, win_y = self.pill.get_current_position()
        win_w, _ = self.pill.get_size()

        # snap coordinates
        x_targets = {
            "left": 0,
            "center": (geo.width - win_w) // 2,
            "right": geo.width - win_w,
        }

        y_targets = {
            "top": 0,
            # "center": (available_height - win_h + dock_offset) // 2,
            # "bottom": available_height - win_h,
        }

        if not fixed:
            target_x_name = min(x_targets, key=lambda k: abs(win_x - x_targets[k]))
            target_y_name = min(y_targets, key=lambda k: abs(win_y - y_targets[k]))

            self.pill.set_position_config(target_x_name, target_y_name)

            target_x = x_targets[target_x_name]
            target_y = y_targets[target_y_name]

            self.layer_choice_for_pill = {"enable": [], "disable": []}
            if target_x_name == "left":
                self.layer_choice_for_pill["enable"].append(GtkLayerShell.Edge.LEFT)
                self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.RIGHT)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.LEFT, True)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.RIGHT, False)
            elif target_x_name == "right":
                self.layer_choice_for_pill["enable"].append(GtkLayerShell.Edge.RIGHT)
                self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.LEFT)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.LEFT, False)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.RIGHT, True)
            else:
                self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.LEFT)
                self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.RIGHT)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.LEFT, False)
                GtkLayerShell.set_anchor(self.top_bar, GtkLayerShell.Edge.RIGHT, False)

            # if target_y_name == "top":
            #     self.layer_choice_for_pill["enable"].append(GtkLayerShell.Edge.TOP)
            #     self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.BOTTOM)
            # elif target_y_name == "bottom":
            #     self.layer_choice_for_pill["enable"].append(GtkLayerShell.Edge.BOTTOM)
            #     self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.TOP)
            # else:
            #     self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.TOP)
            #     self.layer_choice_for_pill["disable"].append(GtkLayerShell.Edge.BOTTOM)

        else:
            pill_position_config = self.pill.get_position_config()
            target_x_name = pill_position_config["x"]
            target_y_name = pill_position_config["y"]

            target_x = x_targets[target_x_name]
            target_y = y_targets[target_y_name]

        if animate:
            self._animate_to_position(target_x, target_y)
        else:
            self.animator.pause()
            self.pill.set_current_position(target_x, target_y)

        self._set_dock_state(None, None, target_x, target_y)

    def _animate_to_position(self, target_x, target_y):
        drag_state = self.pill.get_drag_state()
        if drag_state and drag_state.get("dragging"):
            return

        self.pill_start_x, self.pill_start_y = self.pill.get_current_position()
        self.pill_target_x = target_x
        self.pill_target_y = target_y

        # set up animator
        self.animator.pause()
        self.animator.value = 0
        self.animator.min_value = 0
        self.animator.max_value = 1

        self.animator.play()

    def _apply_position(self, progress_percent):
        current_x = int(
            self.pill_start_x
            + (self.pill_target_x - self.pill_start_x) * progress_percent
        )
        current_y = int(
            self.pill_start_y
            + (self.pill_target_y - self.pill_start_y) * progress_percent
        )
        self.pill.set_current_position(current_x, current_y)

    def _on_snap_finish(self, *_):
        for anchor in self.layer_choice_for_pill["disable"]:
            GtkLayerShell.set_anchor(self.pill, anchor, False)
        for anchor in self.layer_choice_for_pill["enable"]:
            GtkLayerShell.set_anchor(self.pill, anchor, True)

    def _disconnect_geometry_enforcement(self, widget):
        # Disable builtin geometry hooks to allow custom placement and prevent jitter.
        hooks = [
            ("_size_allocate_hook", "handler_disconnect"),
            ("do_dispatch_geometry", None),
        ]

        for attr, action in hooks:
            if hasattr(widget, attr) and getattr(widget, attr):
                try:
                    if action == "handler_disconnect":
                        widget.handler_disconnect(getattr(widget, attr))
                        setattr(widget, attr, None)
                    else:
                        # Override with no-op lambda
                        setattr(widget, attr, lambda: None)
                except Exception as e:
                    logger.debug(f"Could not disconnect {attr}: {e}")

    def _connect_geometry_enforcement(self, widget): ...
