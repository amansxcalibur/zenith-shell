from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.label import Label
from modules.dock.module_overlay import HoverOverlay, HolePlaceholder
from fabric.widgets.eventbox import EventBox
from utils.helpers import toggle_class
from modules.workspaces import Workspaces
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from modules.controls import ControlsManager
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.widgets.x11 import X11Window as Window
from i3ipc import Connection
import subprocess
from modules.systray import SystemTray
from modules.workspaces import Workspaces
from modules.metrics import MetricsSmall, Battery
import config.info as info
import icons.icons as icons
from utils.helpers import toggle_class
from modules.dock.v0.dock_modules import DockModuleOverlay
import time
import gi

from modules.dock.layout_manager import LayoutManager

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk

SPACING = 0


class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry="bottom",
            type_hint="dock",
            margin="0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )

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
        self.vol_small = self.controls.get_volume_small()
        self.brightness_small = self.controls.get_brightness_small()
        self.vol_brightness_box = Box(
            name="vol-brightness-container",
            orientation="h",
            children=[self.vol_small, self.brightness_small],
        )
        self.date_time = Box(
            name="date-time-container",
            style_classes="" if not info.VERTICAL else "vertical",
            children=DateTime(
                name="date-time",
                formatters=["%H\n%M"] if info.VERTICAL else ["%H:%M"],
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
                style_classes="" if not info.VERTICAL else "vertical",
            ),
        )
        self.vertical_toggle_btn = Button(
            name="orientation-btn",
            child=Label(
                name="orientation-label",
                markup=(
                    icons.toggle_vertical
                    if not info.VERTICAL
                    else icons.toggle_horizontal
                ),
            ),
            on_clicked=lambda b, *_: self.toggle_vertical(),
        )
        self.user_modules_left = [
            self.vertical_toggle_btn,
            self.workspaces,
            self.vol_brightness_box,
        ]
        self.user_modules_right = [
            self.systray,
            self.metrics,
            self.battery,
            self.date_time,
        ]
        self.visual_modules_left = [
            Box(
                name="hight",
                style="padding-left:3px; padding-right:3px;",
                children=w,
            )
            for w in self.user_modules_left
        ]
        self.visual_modules_right = [
            Box(
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
            style="min-height:40px;",
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
            style="min-height:40px;",
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

        self.pill = Box(name="vert")

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
        self.pill_container = Box(
            children=[
                self.left_pill_curve,
                Box(
                    name="hori",
                    style_classes="pill",
                    orientation="v",
                    children=[self.pill, Box(name="bottom", v_expand=True)],
                ),
                self.right_pill_curve,
            ]
        )

        self.children = Box(
            name="main",
            children=[self.start_children, self.pill_container, self.end_children],
        )

        size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        size_group.add_widget(self.start_children)
        size_group.add_widget(self.end_children)

    def open(self):
        toggle_class(self.pill, "contractor", "expand")
        toggle_class(self.pill_container, "contractor", "expander")
        toggle_class(self.left_pill_curve, "contractor", "expander")
        toggle_class(self.right_pill_curve, "contractor", "expander")
        self.bool = True

    def close(self):
        toggle_class(self.pill, "expand", "contractor")
        toggle_class(self.pill_container, "expander", "contractor")
        toggle_class(self.left_pill_curve, "expander", "contractor")
        toggle_class(self.right_pill_curve, "expander", "contractor")
        self.bool = False

    def set_hole_state(self, source, event, state: bool, side: str):
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
        subprocess.run([f"{info.HOME_DIR}/i3scripts/flaunch.sh"])
