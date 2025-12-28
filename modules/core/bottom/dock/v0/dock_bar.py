from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.widgets.x11 import X11Window as Window
from i3ipc import Connection

from modules.systray import SystemTray
from modules.workspaces import Workspaces
from modules.metrics import MetricsSmall, Battery
from modules.core.bottom.dock.v0.dock_modules import DockModuleOverlay

import config.info as info
import icons
from utils.helpers import toggle_class

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk
from modules.controls import ControlsManager

import subprocess

class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry="bottom",
            type_hint="dock",
            margin="0px 0px 0px 0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )
        self.bool = False
        self.i3 = Connection()
        if info.VERTICAL:
            self.i3.command("gaps left all set 44px")
            self.i3.command("gaps bottom all set 3px")
        else:
            self.i3.command("gaps left all set 3px")
            self.i3.command("gaps top all set 3px")
            self.i3.command("gaps bottom all set 3px")

        self.workspaces = Workspaces()

        self.metrics = MetricsSmall()
        self.battery = Battery()

        self.systray = SystemTray()

        self.target = Box()

        self.pill = Box(name="vert")

        self.controls = ControlsManager()
        self.vol_small = self.controls.get_volume_small()
        self.brightness_small = self.controls.get_brightness_small()
        self.vol_brightness_box = Box(
            name="vol-brightness-container",
            orientation="h",
            children=[self.vol_small, self.brightness_small],
        )

        self.vertical_toggle_btn = Button(
            name="orientation-btn",
            child=Label(
                name="orientation-label",
                markup=(
                    icons.toggle_orientation.markup()
                ),
            ),
            on_clicked=lambda b, *_: self.toggle_vertical(),
        )

        self.starter_box = Box(
            name="start",
            h_expand=True,
        )

        self.starter_box_2 = Box(
            name="start",
            h_expand=True,
        )

        self.ender_box = Box(
            name="end",
            h_expand=True,
        )

        self.ender_box_2 = Box(
            name="end",
            h_expand=True,
        )

        self.start_modules = [
            self.make_module(self.vertical_toggle_btn, 0),
            self.make_module(self.workspaces, 1),
            self.make_module(self.vol_brightness_box,2),
        ]
        self.end_modules = [
            self.make_module(self.systray, 5),
            self.make_module(self.metrics, 6),
            self.make_module(self.battery, 7),
        ]
        self.modules = [
            *self.start_modules,
            self.starter_box,
            self.ender_box,
            *self.end_modules,
        ]

        self.start = Box(
            h_expand=True,
            children=[
                *self.start_modules,
                self.starter_box,
                self.starter_box_2,
            ],
        )

        self.end = Box(
            h_expand=True,
            children=[self.ender_box_2, self.ender_box, *self.end_modules],
        )

        self.pill_container = Box(
            name="hori",
            orientation="v",
            children=[self.pill, Box(name="bottom", v_expand=True)],
        )

        self.children = Box(
            name="main",
            children=[
                self.start,
                self.pill_container,
                self.end,
            ],
        )

        # SizeGroup to equalize width of start and end children
        size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        size_group.add_widget(self.start)
        size_group.add_widget(self.end)

        self.add_keybinding("Escape", lambda *_: self.close())

    def make_module(self, overlays, index):
        module = DockModuleOverlay(overlays=overlays, id=index)
        module.connect("hole-index", self.on_module_hover)
        return module

    def on_module_hover(self, source, hovered_index, type=None):
        for i, module in enumerate(self.modules):
            is_prev = i == hovered_index - 1
            is_next = i == hovered_index + 1
            is_self = i == hovered_index

            def apply_styles(m, starter_radius, ender_radius, source):
                transition = "0.25s cubic-bezier(0.5, 0.25, 0, 1)"

                if hasattr(m, "starter_box") and hasattr(m, "ender_box"):
                    m.starter_box.set_style(
                        f"border-top-left-radius:{starter_radius}px;"
                        f"transition: border-top-left-radius {transition};"
                    )
                    m.ender_box.set_style(
                        f"border-top-right-radius:{ender_radius}px;"
                        f"transition: border-top-right-radius {transition};"
                    )
                else:
                    m.set_style(
                        f"border-top-left-radius:{starter_radius}px;"
                        f"border-top-right-radius:{ender_radius}px;"
                        f"transition: border-radius {transition};"
                    )

            if is_prev:
                GLib.timeout_add(
                    100, lambda m=module: apply_styles(m, 0, 20, source) or False
                )
            elif is_next:
                GLib.timeout_add(
                    100, lambda m=module: apply_styles(m, 20, 0, source) or False
                )
            elif module != source:
                GLib.timeout_add(
                    0, lambda m=module: apply_styles(m, 0, 0, source) or False
                )
            else:
                print("iam source", module._id, i)
                module.starter_box.set_style(
                    f"transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1), min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                )
                module.ender_box.set_style(
                    f"transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1), min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                )

    def open(self):
        # height increase
        toggle_class(self.pill, "contractor", "expand")
        toggle_class(self.pill_container, "contractor", "expander")
        toggle_class(self.starter_box_2, "contractor", "expander")
        toggle_class(self.ender_box_2, "contractor", "expander")
        self.bool = True

    def close(self):
        toggle_class(self.pill, "expand", "contractor")
        toggle_class(self.pill_container, "expander", "contractor")
        toggle_class(self.starter_box_2, "expander", "contractor")
        toggle_class(self.ender_box_2, "expander", "contractor")
        self.bool = False

    def toggle_vertical(self):
        # toggle_config_vertical_flag()
        # restart bar
        subprocess.run([f"{info.HOME_DIR}/i3scripts/flaunch.sh"])