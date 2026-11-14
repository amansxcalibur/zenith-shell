from __future__ import annotations

from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pill import Pill
    from .dock.bar import DockBar

from services.animator import Animator

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk  # type: ignore


class ShellWindowManager:
    DOCK_GAP = 3  # px between the dock and a pill floating above it

    @property
    def pill_widget(self):
        return self.pill

    @property
    def dock_widget(self):
        return self.dockBar

    def __init__(self, pill: Pill, dockBar: DockBar):
        if not pill or not dockBar:
            raise ValueError(
                "ShellWindowManager requires both 'pill' and 'dockBar' instances."
            )

        self.pill = pill
        self.dockBar = dockBar

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
        )

        self.pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        self._setup_size_groups()

        # Connect signals
        self.pill.connect("on-drag", self._set_dock_state)
        self.pill.connect("on-drag-end", lambda w, state: self._snap_pill())
        self.pill.pill_container.connect("size-allocate", self._on_pill_resized)
        self.dockBar.connect("insets-changed", self._on_dock_insets_changed)

        self._disconnect_geometry_enforcement(self.pill)
        self.pill.canvas.set_placement_func(self._placement_for_size)

    def _setup_size_groups(self):
        # only a dock that seats the pill has a slot to match its width
        if self.dockBar.pill_dock is None:
            return
        self.pill_size_group.add_widget(self.dockBar.pill_dock)
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

    def _bottom_offset(self) -> int:
        # room above a bottom dock; 0 when the dock is hidden or on a side
        bottom = self.dockBar.insets.bottom
        return bottom + self.DOCK_GAP if bottom else 0

    def _on_dock_insets_changed(self, *args):
        self._snap_pill()

    def _is_dragging(self) -> bool:
        drag_state = self.pill.get_drag_state()
        return bool(drag_state and drag_state.get("dragging"))

    def _placement_for_size(self, win_w: int, win_h: int) -> tuple[int, int] | None:
        # the canvas asks with every new size, in the frame that paints it;
        # dragging and the snap animation move the pill themselves
        if self._is_dragging() or self.animator.playing:
            return None
        return self.pill.to_canvas(
            *self._target_position(
                win_w, win_h, self.pill._pos["x"], self.pill._pos["y"]
            )
        )

    def _on_pill_resized(self, widget, allocation):
        if self._is_dragging() or self.animator.playing:
            return
        # the canvas has placed it already; only the dock needs to know
        self._set_dock_state(None, None, *self.pill.get_current_position())

    def _set_dock_state(self, source, drag_state, x: int, y: int):
        if not self.dockBar.placement.seats_pill:
            return

        geo = self._get_monitor_geometry(self.pill)
        win_w, win_h = self.pill.get_pill_size()

        # x and y are root coordinates; the monitor may not start at 0,0
        dock_top = geo.y + geo.height - self.dockBar.surface.thickness - self.DOCK_GAP
        pill_is_in_dock_zone = (y + win_h) > dock_top and (
            # judge by the pill's centre: a wide centred pill has its left
            # edge outside the middle half of the screen
            geo.width // 4 < x - geo.x + win_w // 2 < 3 * geo.width // 4
        )

        if pill_is_in_dock_zone:
            self.dockBar.override_reset()
        else:
            self.dockBar.override_close()

    def _snap_targets(self, win_w: int, win_h: int):
        """Root coordinates of each snap column and row for a pill this size."""
        geo = self._get_monitor_geometry(self.pill)
        insets = self.dockBar.insets
        available_height = geo.height - self._bottom_offset()

        x_targets = {
            "left": geo.x + insets.left,
            "center": geo.x + (geo.width - win_w) // 2,
            "right": geo.x + geo.width - win_w - insets.right,
        }
        y_targets = {
            "top": geo.y,
            "center": geo.y + (available_height - win_h) // 2,
            "bottom": geo.y + available_height - win_h,
        }
        return x_targets, y_targets

    def _target_position(
        self, win_w: int, win_h: int, x_name: str, y_name: str
    ) -> tuple[int, int]:
        x_targets, y_targets = self._snap_targets(win_w, win_h)
        target_x, target_y = x_targets[x_name], y_targets[y_name]

        # bottom center sits INSIDE the dock; the dock's module rows clip
        # under the hole when the pill is wider than the free space
        if self.dockBar.placement.seats_pill and (x_name, y_name) == (
            "center",
            "bottom",
        ):
            target_y += self._bottom_offset()

        return target_x, target_y

    def _snap_pill(self, animate: bool = True, fixed: bool = False):
        if self._is_dragging():
            return

        win_x, win_y = self.pill.get_current_position()
        win_w, win_h = self.pill.get_pill_size()

        if fixed:
            target_x_name = self.pill._pos["x"]
            target_y_name = self.pill._pos["y"]
        else:
            x_targets, y_targets = self._snap_targets(win_w, win_h)
            target_x_name = min(x_targets, key=lambda k: abs(win_x - x_targets[k]))
            target_y_name = min(y_targets, key=lambda k: abs(win_y - y_targets[k]))
            self.pill.set_position_config(target_x_name, target_y_name)

        target_x, target_y = self._target_position(
            win_w, win_h, target_x_name, target_y_name
        )

        if animate:
            self._animate_to_position(target_x, target_y)
        else:
            self.animator.pause()
            self.pill.set_current_position(target_x, target_y)

        self._set_dock_state(None, None, target_x, target_y)

    def _animate_to_position(self, target_x, target_y):
        if self._is_dragging():
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
