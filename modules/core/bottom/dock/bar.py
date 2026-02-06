from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.datetime import DateTime

from widgets.material_label import MaterialIconLabel
from widgets.overrides import PatchedX11Window as Window

from modules.systray import SystemTray
from modules.weather import WeatherMini
from modules.workspaces import Workspaces
from modules.controls import ControlsManager
from modules.metrics import MetricsSmall, Battery
from modules.core.bottom.dock.layout_manager import LayoutManager
from modules.core.bottom.dock.module_overlay import HoverOverlay, HolePlaceholder

import icons
from config.info import config
from utils.helpers import toggle_class
from utils.cursor import add_hover_cursor

import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

SPACING = 0


class DockBar(Window):
    WIN_ROLE = "zenith-dock"

    def __init__(self, pill, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry=config.bar["POSITION"],
            type_hint="dock",
            margin="0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )
        self.set_title(self.WIN_ROLE)

        self._pill_ref = pill

        self.is_open = False
        self._pill_is_docked = True

        self.hole_state_left = False
        self.hole_state_right = False

        self.layout_manager_left = LayoutManager(self, side="left")
        self.layout_manager_right = LayoutManager(self, side="right")
        self.init_modules()
        self.layout_manager_left.init_layout()
        self.layout_manager_right.init_layout()
        self.build_bar()

        self.add_keybinding("Escape", lambda *_: self.close())

    def init_modules(self):
        self.workspaces = Workspaces()
        self.controls = ControlsManager()
        self.systray = SystemTray()
        self.metrics = MetricsSmall()
        self.battery = Battery()
        self.weather_mini = WeatherMini()
        self.vol_brightness_box = self.controls.get_controls_box()
        self.date_time = Box(
            name="date-time-container",
            style_classes="" if not config.VERTICAL else "vertical",
            v_expand=True,
            children=DateTime(
                name="date-time",
                formatters=(
                    ["%H\n%M"]
                    if config.VERTICAL
                    else ["%I:%M %p", "%H:%M", "%A", "%m-%d-%Y"]
                ),
            ),
        )
        self.vertical_toggle_btn = add_hover_cursor(
            Button(
                name="orientation-btn",
                child=MaterialIconLabel(
                    name="orientation-label",
                    FILL=0,
                    icon_text=(icons.toggle_orientation.symbol()),
                ),
                on_clicked=lambda b, *_: self.toggle_vertical(),
            )
        )
        self.user_modules_left = [
            self.vertical_toggle_btn,
            self.workspaces,
            self.vol_brightness_box,
            self.weather_mini,
            self.metrics,
        ]
        self.user_modules_right = [
            self.systray,
            self.battery,
            self.date_time,
        ]
        self.visual_modules_left = [
            Box(
                name="dock-module",
                style="padding-left:3px; padding-right:3px;",
                children=w,
            )
            for w in self.user_modules_left
        ]
        self.visual_modules_right = [
            Box(
                name="dock-module",
                style="padding-left:3px; padding-right:3px;",
                children=w,
            )
            for w in self.user_modules_right
        ]

        self.placeholders_left = [
            HolePlaceholder(
                target=mod, edge_flag=(i == len(self.visual_modules_left) - 2)
            )
            for i, mod in enumerate(self.visual_modules_left)
        ]
        self.placeholders_right = [
            HolePlaceholder(
                target=mod, edge_flag=(i == len(self.visual_modules_right) - 2)
            )
            for i, mod in enumerate(self.visual_modules_right)
        ]

        self.hover_overlay_row_left = Box(
            style="min-height:41px;",  # (40+1)px cuz 1.5px margins is replaced with 2px
            spacing=SPACING,
            h_expand=True,
            children=[
                HoverOverlay(
                    target_box=mod,
                    hole_box=hole,
                    layout_manager=self.layout_manager_left,
                    id=i,
                )
                for i, (mod, hole) in enumerate(
                    zip(self.visual_modules_left, self.placeholders_left)
                )
            ],
        )
        self.edge_fallback_right = EventBox(
            h_expand=True,
            child=Box(h_expand=True),
            events=["enter-notify"],
        )

        self.hover_overlay_row_right = Box(
            style="min-height:41px;",
            spacing=SPACING,
            h_expand=True,
            children=[self.edge_fallback_right],  # fallback first
        )

        for i, (mod, hole) in enumerate(
            zip(self.visual_modules_right, self.placeholders_right)
        ):
            self.hover_overlay_row_right.add(
                HoverOverlay(
                    target_box=mod,
                    hole_box=hole,
                    layout_manager=self.layout_manager_right,
                    id=i,
                )
            )

        for i, module in enumerate(self.hover_overlay_row_left.children):
            module.connect(
                "hole-index",
                lambda w, v, side="left": self.handle_hover(w, v, side=side),
            )

        for i, module in enumerate(self.hover_overlay_row_right.children):
            if i > 0:
                module.connect(
                    "hole-index",
                    lambda w, v, side="right": self.handle_hover(w, v, side=side),
                )

        self.pill_dock = Box(name="vert")

        self.edge_fallback_left = EventBox(
            h_expand=True,
            child=Box(h_expand=True),
            events=["enter-notify"],
        )
        self.edge_fallback_left.connect(
            "enter-notify-event", lambda w, e: self.set_hole_state(w, e, False, "left")
        )
        self.edge_fallback_right.connect(
            "enter-notify-event", lambda w, e: self.set_hole_state(w, e, False, "right")
        )
        self.hover_overlay_row_left.add(self.edge_fallback_left)

    def build_bar(self):
        self.start_children = Box(
            h_expand=True, children=self.layout_manager_left.event_wrapper
        )
        self.end_children = Box(
            h_expand=True,
            children=self.layout_manager_right.event_wrapper,
        )
        self.left_pill_curve = Box(name="start", h_expand=True)
        self.right_pill_curve = Box(name="end", h_expand=True)
        self.pill_dock_container = Box(
            children=[
                self.left_pill_curve,
                Box(
                    name="hori",
                    style_classes="pill",
                    orientation="v",
                    children=[self.pill_dock, Box(name="bottom", v_expand=True)],
                ),
                self.right_pill_curve,
            ]
        )
        self.compact = Box(
            style="min-width:1px; min-height:1px; background-color:black"
        )
        self.stack = Stack(
            transition_duration=300,
            transition_type="over-up",
            children=[self.pill_dock_container, self.compact],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = Box(
            name="main",
            children=[self.start_children, self.stack, self.end_children],
        )

        size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        size_group.add_widget(self.start_children)
        size_group.add_widget(self.end_children)

    def get_is_open(self):
        return self.is_open

    def set_pill_docked(self, docked: bool):
        self._pill_is_docked = docked

    def override_close(self):
        self._pill_is_docked = False
        self.stack.set_visible_child(self.compact)
        self._apply_close_visual()

    def override_reset(self):
        self._pill_is_docked = True
        self.stack.set_visible_child(self.pill_dock_container)
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
        toggle_class(self.pill_dock, "contractor", "expand")
        toggle_class(self.pill_dock_container, "contractor", "expander")
        toggle_class(self.left_pill_curve, "contractor", "expander")
        toggle_class(self.right_pill_curve, "contractor", "expander")

    def _apply_close_visual(self):
        toggle_class(self.pill_dock, "expand", "contractor")
        toggle_class(self.pill_dock_container, "expander", "contractor")
        toggle_class(self.left_pill_curve, "expander", "contractor")
        toggle_class(self.right_pill_curve, "expander", "contractor")

    def set_hole_state(self, source, event, state: bool, side: str):
        # this function solely exist to reset and collapse the hole when the cursor travels to
        # the edge within the bar(see edge_fallback) because ModuleOverlay.unhover() ignores events that are INFERIOR
        if side == "left":
            self.layout_manager_left.set_hole_state(source, event, state)
        else:
            self.layout_manager_right.set_hole_state(source, event, state)

    def handle_hover(self, source, id: int, side: str):
        if side == "left":
            self.layout_manager_left.handle_hover(source, id)
        else:
            self.layout_manager_right.handle_hover(source, id)

    def toggle_vertical(self):
        # toggle_config_vertical_flag()
        # restart bar
        subprocess.run([f"{config.SCRIPTS_DIR}/flaunch.sh"])

    def toggle_visibility(self):
        visible = not self.is_visible()
        self.set_visible(visible)
        self._pill_ref._dock_is_visible = visible
