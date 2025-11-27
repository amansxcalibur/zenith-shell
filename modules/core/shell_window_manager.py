from loguru import logger

from services.animator import Animator

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


class ShellWindowManager:
    DOCK_HEIGHT = 43

    def __init__(self, pill, dockBar):
        if not pill or not dockBar:
            raise ValueError(
                "ShellWindowManager requires both 'pill' and 'dockBar' instances."
            )

        self.pill = pill
        self.dockBar = dockBar

        self.pill_start_x, self.pill_start_y = self.pill.get_position()
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
        self.pill.connect("size-allocate", self._on_pill_resized)
        self.dockBar.connect("notify::visible", self._on_dock_visibility_toggle)

        self._disconnect_geometry_enforcement(self.pill)

    def _setup_size_groups(self):
        self.pill_size_group.add_widget(self.dockBar.pill_dock)
        self.pill_size_group.add_widget(self.pill.pill_container)

    def _remove_size_groups(self):
        self.pill_size_group.remove_widget(self.pill.pill_container)

    # -- Properties --
    @property
    def pill_widget(self):
        return self.pill

    @property
    def dock_widget(self):
        return self.dockBar

    def _get_monitor_geometry(self, widget):
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_window(widget.get_window())
        return monitor.get_geometry()

    def _is_dock_visible(self):
        return self.dockBar.get_visible()

    def _on_dock_visibility_toggle(self, *args):
        self._snap_pill()

    def _on_pill_resized(self, widget, allocation):
        # Currently dragging, don't snap
        drag_state = self.pill.get_drag_state()
        if drag_state and drag_state.get("dragging"):
            return

        if self.animator.playing:
            return
        
        self._snap_pill(animate=False, fixed=True)

    def _set_dock_state(self, source, drag_state, x: int, y: int):
        geo = self._get_monitor_geometry(self.pill)
        win_w, win_h = self.pill.get_size()

        pill_is_in_dock_zone = (y + win_h) > (geo.height - self.DOCK_HEIGHT) and (
            geo.width // 4 < x < 3 * geo.width // 4
        )

        if pill_is_in_dock_zone:
            self.dockBar.override_reset()
        else:
            self.dockBar.override_close()

    def _snap_pill(self, animate: bool = True, fixed: bool = False):
        geo = self._get_monitor_geometry(self.pill)
        win_x, win_y = self.pill.get_position()
        win_w, win_h = self.pill.get_size()

        dock_offset = self.DOCK_HEIGHT if self._is_dock_visible() else 0
        available_height = geo.height - dock_offset

        # snap coordinates
        x_targets = {
            "left": 0,
            "center": (geo.width - win_w) // 2,
            "right": geo.width - win_w,
        }

        y_targets = {
            "top": 0,
            "middle": (available_height - win_h) // 2,
            "bottom": available_height - win_h,
        }

        if not fixed:
            target_x_name = min(x_targets, key=lambda k: abs(win_x - x_targets[k]))
            target_y_name = min(y_targets, key=lambda k: abs(win_y - y_targets[k]))

            # CHANGES THE CONFIG!!
            self.pill._pos['x'] = target_x_name
            self.pill._pos['y'] = target_y_name

            target_x = x_targets[target_x_name]
            target_y = y_targets[target_y_name]
        
        else:
            target_x_name = self.pill._pos['x']
            target_y_name = self.pill._pos['y']

            target_x = x_targets[target_x_name]
            target_y = y_targets[target_y_name]

        # If snapping to bottom and dock is open, push it down into the dock
        if target_y_name == "bottom" and target_x_name == "center":
            target_y += dock_offset

        if animate:
            self._update_target_position(target_x, target_y)
        else:
            self.animator.pause()
            self.pill.move(target_x, target_y)

        self._set_dock_state(None, None, target_x, target_y)

    def _update_target_position(self, target_x, target_y):
        drag_state = self.pill.get_drag_state()
        if drag_state and drag_state.get("dragging"):
            return

        self.pill_start_x, self.pill_start_y = self.pill.get_position()
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
        self.pill.move(current_x, current_y)

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
