import fabric
from fabric import Application
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.datetime import DateTime
from fabric.widgets.x11 import X11Window as Window
from fabric.utils import get_relative_path
from fabric.utils.helpers import exec_shell_command_async
from i3ipc import Connection

from launcher import AppLauncher
from corner import Corners, MyCorner
from fabric.widgets.revealer import Revealer
from systray import SystemTray
from workspaces import Workspaces, ActiveWindow
from metrics import MetricsSmall, Battery
from player import PlayerContainer
import info
import icons.icons as icons

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk
from wallpaper import WallpaperSelector
from volume import VolumeSlider, VolumeSmall
from brightness import BrightnessSlider, BrightnessSmall
from controls import ControlsManager
from utilities.cursor import add_hover_cursor

import os, subprocess

class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="top" if not info.VERTICAL else "bottom",
            geometry="bottom" if not info.VERTICAL else "left",
            type_hint="normal" if info.VERTICAL else "dock",
            margin="0px 0px 0px 0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs
        )
        self.bool = False
        self.i3 = Connection()
        if info.VERTICAL:
            self.i3.command("gaps left all set 44px")
            self.i3.command("gaps bottom all set 3px")
        else:
            self.i3.command("gaps left all set 3px")
            self.i3.command("gaps top all set 3px")
            self.i3.command("gaps bottom all set 0px")

        self.workspaces = Workspaces()

        self.metrics = MetricsSmall()
        self.battery = Battery()

        self.systray = SystemTray()

        self.pill = Box(name="vert")

        self.start = Box(
            name="start",
            h_expand=True,
            children=[
                self.workspaces,
            ]
        )

        self.end = Box(
            name="end",
            h_expand=True,
            children=Box(
                name="inner-end",
                h_expand=True,
                h_align="end",
                children=[
                    self.systray,
                    self.metrics,
                    self.battery
                ]
            )
        )

        self.pill_container = Box(
            name="hori",
            orientation='v',
            children=[
                self.pill,
                Box(name="bottom", v_expand=True)
            ]
        )

        self.children = Box(
            name ="main", 
            children=[
                self.start,
                self.pill_container,
                self.end,
            ]
        )

        # SizeGroup to equalize width of start and end children
        size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        size_group.add_widget(self.start)
        size_group.add_widget(self.end)

        self.add_keybinding("Escape", lambda *_: self.close())

    def open(self):
        if self.bool == False:
            self.pill.remove_style_class("contractor")
            self.pill_container.remove_style_class("contractor")
            self.start.remove_style_class("contractor")
            self.end.remove_style_class("contractor")

            self.pill.add_style_class("expand")
            self.pill_container.add_style_class("expander")
            self.start.add_style_class("expander")
            self.end.add_style_class("expander")
            self.bool = True
        else:
            self.pill.remove_style_class("expand")
            self.pill_container.remove_style_class("expander")
            self.start.remove_style_class("expander")
            self.end.remove_style_class("expander")
            
            self.pill.add_style_class("contractor")
            self.pill_container.add_style_class("contractor")
            self.start.add_style_class("contractor")
            self.end.add_style_class("contractor")
            self.bool = False

class Notch(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notch",
            layer="top",
            geometry="bottom" if not info.VERTICAL else "left",
            type_hint="normal",
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self.bool = False
        self.player = PlayerContainer()
        self.player.add_style_class("hide-player")
        self.text = Label(label="hele", name="text")
        self.children = Box(
            name="pill-container",
            children=self.player
        )

    def toggle_player(self, *_):
        if self.bool == False:
            # exec_shell_command_async('i3-msg [class="Negative_margin.py"] focus')
            exec_shell_command_async('i3-msg [window_role="notch"] focus')
            self.player.remove_style_class("hide-player")
            self.player.add_style_class("reveal-player")
            self.bool = True
            # self.stack.set_visible_child(self.player)
        else:
            self.player.remove_style_class("reveal-player")
            self.player.add_style_class("hide-player")
            # self.stack.set_visible_child(self.collapsed)
            self.bool = False

if __name__ == "__main__":
    notch = Notch()
    bar = DockBar()
    notch.set_role("notch")
    bar.notch = notch
    if info.VERTICAL:
        bar.set_title("fabric-dock")
        # make the window consume all vertical space
        monitor = bar._display.get_primary_monitor()
        rect = monitor.get_geometry()
        scale = monitor.get_scale_factor()
        bar.set_size_request(0, rect.height * scale)
        bar.show_all()
        # bar.show_all()
        # bar.set_keep_above(True)


    app = Application("bar-example", bar, notch, open_inspector=False)
    
    def set_css():
        app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))
    app.set_css = set_css
    app.set_css()

    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()