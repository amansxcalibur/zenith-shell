from __future__ import annotations

from loguru import logger
from typing import TYPE_CHECKING

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.core.service import Signal

from config.config import config
from config.info import IS_WAYLAND

from modules.special import DateTime
from modules.systray import SystemTray
from modules.weather import WeatherMini
from modules.special import ActionButton
from modules.controls import ControlsManager
from modules.workspaces.workspaces import Workspaces
from modules.power_profiles import PowerProfilesSelector
from modules.metrics.metrics import MetricsSmall, Battery

from utils.colors import bind_theme
from utils.cursor import add_hover_cursor

from widgets.edge_clip_viewport import EdgeClipViewport

from .hole_controller import HoleController
from .placement import DockInsets, DockEdge, current_placement
from .surface import HOLE_FLARE, DockSurface

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # type: ignore

if IS_WAYLAND:
    from fabric.widgets.wayland import WaylandWindow as Window
else:
    from widgets.overrides import PatchedX11Window as Window

if TYPE_CHECKING:
    from ..pill import Pill

PILL_HOLE_RADIUS = 25  # px, 2px larger than the pill's own corners


class DockBar(Window):
    WIN_ROLE = "zenith-dock"

    @Signal
    def insets_changed(self): ...

    def __init__(self, pill: Pill, **kwargs):
        self.placement = current_placement()

        if IS_WAYLAND:
            super().__init__(
                layer="bottom",
                title=self.WIN_ROLE,
                anchor=self.placement.layer_anchor,
                exclusivity="auto",
                pass_through=False,
                visible=True,
                all_visible=True,
                **kwargs,
            )
        else:
            super().__init__(
                name="dock-bar",
                layer="bottom",
                title=self.WIN_ROLE,
                geometry=self.placement.edge.value,
                # i3 only reserves room for "dock" windows at the top or bottom;
                # on a side the window floats and i3's gaps make the room
                type_hint="notification" if self.placement.vertical else "dock",
                visible=True,
                all_visible=True,
                h_expand=True,
                v_expand=True,
                **kwargs,
            )
            self.set_role(self.WIN_ROLE)

        self._pill_ref = pill
        pill.dock_bar = self  # lets the pill open/close us directly

        bind_theme(self)

        self.is_open = False
        self._pill_is_docked = True
        self._last_insets: DockInsets | None = None

        self.init_modules()
        self.build_bar()
        if not IS_WAYLAND and self.placement.vertical:
            self._fill_screen_side()
            self.connect("configure-event", self._on_side_dock_configured)

        self._last_insets = self.insets
        self.connect("notify::visible", lambda *_: self._check_insets())
        self.surface.connect("size-allocate", self._on_surface_allocated)

        self.add_keybinding("Escape", lambda *_: self.close())
        self.show_all()

    def init_modules(self):
        self.controls = ControlsManager()
        vertical = self.placement.vertical

        self.module_map = {
            "workspaces": lambda: Workspaces(vertical=vertical),
            "systray": lambda: SystemTray(vertical=vertical),
            "metrics": lambda: MetricsSmall(vertical=vertical),
            "battery": lambda: Battery(vertical=vertical),
            "weather_mini": lambda: WeatherMini(vertical=vertical),
            "vol_brightness_box": lambda: self.controls.get_controls_box(
                vertical=vertical
            ),
            "date_time": lambda: Box(
                name="date-time-container",
                style_classes="vertical" if vertical else "",
                orientation="v" if vertical else "h",
                v_expand=True,
                children=DateTime(
                    name="date-time",
                    formatters=(
                        ["%H\n%M"]
                        if vertical
                        else ["%I:%M %p", "%H:%M", "%A", "%m-%d-%Y"]
                    ),
                ),
            ),
            "actions": lambda: add_hover_cursor(
                ActionButton(
                    popup_align="end"
                    if self.placement.edge is DockEdge.RIGHT
                    else "start"
                )
            ),
            "power_profiles": PowerProfilesSelector,
        }

        self.modules_start = self._load_modules(config.get("bar.modules.left"))
        self.modules_end = self._load_modules(config.get("bar.modules.right"))[::-1]

    def _load_modules(self, names: list[str]) -> list[Box]:
        modules = []
        for name in names:
            if name not in self.module_map:
                logger.warning(
                    f"[Warning] Module '{name}' is not defined in module_map."
                )
                continue
            try:
                widget = self.module_map[name]()
            except Exception as e:
                logger.error(f"[Error] Failed to initialize module '{name}': {e}")
                continue

            module = Box(
                name="dock-module",
                orientation=self.placement.orientation,
                children=widget,
            )
            # dock modules raise their content on hover; anchor popups to the
            # module box, which stays put, so they don't bob with the raise
            module.is_popup_anchor = True
            modules.append(module)
        return modules

    def build_bar(self):
        self.surface = DockSurface(self.placement)

        # holes are drawn in the order they're added, so this order matters
        self.holes_start = HoleController(
            self.surface, self.placement, self.modules_start, side="start"
        )
        self.pill_hole = (
            self.surface.add_hole(radius=PILL_HOLE_RADIUS)
            if self.placement.seats_pill
            else None
        )
        self.holes_end = HoleController(
            self.surface, self.placement, self.modules_end, side="end"
        )

        # the module rows may shrink below their natural size: when the pill
        # hole (size-grouped with the pill) needs more room than is free,
        # it slides over the inner ends of the rows instead of overflowing
        self.start_clip = self._clip_row(self.holes_start, edge="start")
        self.end_clip = self._clip_row(self.holes_end, edge="end")

        if self.placement.seats_pill:
            self.surface.children = [
                self.start_clip,
                self._build_pill_slot(),
                self.end_clip,
            ]
            # equal sides keep the hole centred
            size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
            size_group.add_widget(self.start_clip)
            size_group.add_widget(self.end_clip)
        else:
            self.pill_dock = None
            self.stack = None
            self.surface.children = [self.start_clip, self.end_clip]

        self.children = self.surface

    def _clip_row(self, holes: HoleController, edge: str) -> EdgeClipViewport:
        clip = EdgeClipViewport(
            holes.widget,
            edge=edge,
            orientation=self.placement.orientation,
            **self.placement.expand_along(),
        )
        holes.set_clip(clip)
        return clip

    def _build_pill_slot(self) -> Stack:
        # transparent spacer that takes the pill's width; the surface cuts the
        # hole around it. The pads keep the hole's flares clear of the rows.
        self.pill_dock = Box(name="dock-pill-slot")
        self.pill_slot = Box(
            children=[
                Box(name="dock-pill-pad", h_expand=True),
                self.pill_dock,
                Box(name="dock-pill-pad", h_expand=True),
            ]
        )
        self.compact = Box(style="min-width:1px; min-height:1px;")
        self.stack = Stack(
            transition_duration=300,
            transition_type="over-up",
            children=[self.pill_slot, self.compact],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)
        return self.stack

    def _fill_screen_side(self):
        # a floating X11 window isn't stretched by the window manager
        monitor = Gdk.Display.get_default().get_primary_monitor()
        self.set_size_request(-1, monitor.get_geometry().height)

    def _on_side_dock_configured(self, _window, event) -> bool:
        # i3 widens a floating window to at least 75px when it starts managing
        # it, as it does for every window on restart. It doesn't apply that
        # minimum to a resize the window asks for, so ask for the rail's width.
        if event.width != self.get_preferred_width().natural_width:
            GLib.idle_add(self._restore_side_dock_width)
        return False

    def _restore_side_dock_width(self) -> bool:
        window = self.get_window()
        if window is not None:
            window.resize(self.get_preferred_width().natural_width, window.get_height())
        return False

    @property
    def insets(self) -> DockInsets:
        """Room the dock currently takes from each side of the screen."""
        thickness = self.surface.thickness if self.get_visible() else 0
        match self.placement.edge:
            case DockEdge.LEFT:
                return DockInsets(left=thickness)
            case DockEdge.RIGHT:
                return DockInsets(right=thickness)
            case _:
                return DockInsets(bottom=thickness)

    def _check_insets(self) -> None:
        insets = self.insets
        if insets != self._last_insets:
            self._last_insets = insets
            # other windows move in response; not during this allocation
            GLib.idle_add(self._emit_insets_changed)

    def _emit_insets_changed(self) -> bool:
        self.insets_changed()
        return False

    def _on_surface_allocated(self, *_):
        self.holes_start.sync_geometry()
        self.holes_end.sync_geometry()
        self._sync_pill_hole()
        self._check_insets()

    def _sync_pill_hole(self) -> None:
        if self.pill_hole is None or not self.pill_dock.get_mapped():
            return

        # mid transition the slot keeps its width and drifts with the stack's edge
        if not self._pill_is_docked or self.stack.get_transition_running():
            return

        along = self.surface.rect_along(self.pill_dock)
        if along is None:
            return

        # the pill drives this width as it animates, so follow it exactly
        start, size = along
        current = self.pill_hole.current
        if (start, size) != (current.start, current.size):
            self.pill_hole.jump_to(start=start, size=size)
        if self.pill_hole.target.depth > 0:
            self.pill_hole.animate_to(depth=self.surface.thickness)

    def get_is_open(self):
        return self.is_open

    def set_pill_docked(self, docked: bool):
        self._pill_is_docked = docked

    def override_close(self):
        if not self.placement.seats_pill:
            return
        self._pill_is_docked = False
        self.stack.set_visible_child(self.compact)
        target = self.pill_hole.target
        self.pill_hole.animate_to(
            start=target.start + target.size / 2, size=0, depth=0, flare=0
        )

    def override_reset(self):
        if not self.placement.seats_pill:
            return
        if not self._pill_is_docked:
            # reopen around the centre the hole closed to
            target = self.pill_hole.target
            size = self.pill_dock.get_preferred_width().natural_width
            self.pill_hole.animate_to(
                start=target.start + (target.size - size) / 2, size=size
            )
        self._pill_is_docked = True
        self.stack.set_visible_child(self.pill_slot)
        if self.is_open:
            self._apply_open_visual()
        else:
            self._apply_close_visual()

    def open(self):
        self.is_open = True
        if self._pill_is_docked:
            self._apply_open_visual()

    def close(self):
        self.is_open = False
        if self._pill_is_docked:
            self._apply_close_visual()

    def _apply_open_visual(self):
        if self.pill_hole is not None:
            self.pill_hole.animate_to(depth=self.surface.thickness, flare=HOLE_FLARE)

    def _apply_close_visual(self):
        if self.pill_hole is not None:
            self.pill_hole.animate_to(depth=0, flare=0)

    def toggle_visibility(self):
        visible = not self.is_visible()
        self.set_visible(visible)
        self._pill_ref._dock_is_visible = visible
