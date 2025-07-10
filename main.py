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

from modules.launcher import AppLauncher
# from corner import Corners, MyCorner
from fabric.widgets.revealer import Revealer
from modules.systray import SystemTray
from modules.workspaces import Workspaces, ActiveWindow
from modules.metrics import MetricsSmall, Battery
from modules.player import PlayerContainer
import config.info as info
import icons.icons as icons
from utils.helpers import toggle_class

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk
from modules.wallpaper import WallpaperSelector
from modules.volume import VolumeSlider, VolumeSmall
from modules.brightness import BrightnessSlider, BrightnessSmall
from modules.controls import ControlsManager
from utils.cursor import add_hover_cursor

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
            self.i3.command("gaps bottom all set 3px")

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
        # height increase
        toggle_class(self.pill, "contractor", "expand")
        # toggle_class(self.pill_container, "contractor", "expander")
        toggle_class(self.start, "contractor", "expander")
        toggle_class(self.end, "contractor", "expander")
        self.bool = True

    def close(self):
        toggle_class(self.pill, "expand", "contractor")
        # toggle_class(self.pill_container, "expander", "contractor")
        toggle_class(self.start, "expander", "contractor")
        toggle_class(self.end, "expander", "contractor")
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
        self.user = Label(label="aman@brewery" if not info.VERTICAL else "am\nan\n@\nbr\new\ner\ny", name="user-label")
        self.dot_placeholder = Label(label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", name="collapsed-bar")
        self.launcher = AppLauncher(notch = self)
        self.launcher.add_style_class("launcher-contract-init")
        self.wallpaper = WallpaperSelector(notch = self)
        self.wallpaper.add_style_class("wallpaper-contract")
        self.text = Label(label="hele", name="text")
        self.stack = Stack(
            name="pill-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[
                self.dot_placeholder,
                self.user,
                self.launcher,
                self.player,
                self.wallpaper
            ]
        )
        self.children = self.stack

    def focus_notch(self):
        # exec_shell_command_async('i3-msg [class="Negative_margin.py"] focus')
        exec_shell_command_async('i3-msg [window_role="notch"] focus')

    def open(self):
        self.focus_notch()
        print(self.stack.get_visible_child().get_name(), self.dot_placeholder.get_name(),self.stack.get_visible_child() == self.dot_placeholder)
        exec_shell_command_async(" fabric-cli exec bar-example 'bar.open()'")
        if self.stack.get_visible_child() == self.dot_placeholder:
            # open launcher
            self.launcher.remove_style_class("launcher-contract-init")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.launcher)
            
            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

        elif self.stack.get_visible_child() == self.player:
            self.player.remove_style_class("reveal-player")
            # self.player.add_style_class("hide-player")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.launcher)
            
            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

    def close(self, *_):
        print("here")
        if self.stack.get_visible_child() == self.player:
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            else:
                self.player.add_style_class("hide-player")
            
            self.stack.set_visible_child(self.dot_placeholder)

        elif self.stack.get_visible_child() != self.dot_placeholder:
            self.stack.remove_style_class("expand")
            exec_shell_command_async(" fabric-cli exec bar-example 'dockBar.reveal_overlapping_modules()'")
            exec_shell_command_async(" fabric-cli exec bar-example 'bar.close()'")
            
            # self.unsteal_input()
            self.wallpaper.remove_style_class("wallpaper-expand")
            self.wallpaper.add_style_class("wallpaper-contract")

            self.stack.add_style_class("contract")

            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.dot_placeholder)
            exec_shell_command_async(f'i3-msg focus mode_toggle')
            # self.launcher.close_launcher()
         
        # for cases where player->dmenu->close()
        if info.VERTICAL:
            self.player.add_style_class("vertical")
        else:
            self.player.add_style_class("hide-player")
        self.show_all()

    def toggle_player(self, *_):
        if self.bool == False:
            self.focus_notch()
            self.player.remove_style_class("hide-player")
            self.player.add_style_class("reveal-player")
            self.bool = True
            # self.stack.set_visible_child(self.player)
        else:
            self.player.remove_style_class("reveal-player")
            self.player.add_style_class("hide-player")
            # self.stack.set_visible_child(self.collapsed)
            self.bool = False

    def open_notch(self, mode):
        match mode:
            case "wallpapers":
                exec_shell_command_async(
                    " fabric-cli exec bar-example 'dockBar.hide_overlapping_modules()'"
                )
                self.remove_style_class("launcher-contract")
                # self.dashboard.add_style_class("hide")

                self.wallpaper.remove_style_class("wallpaper-init")
                toggle_class(self.wallpaper, "wallpaper-contract", "wallpaper-expand")

                self.stack.set_visible_child(self.wallpaper)
            case "dashboard":
                self.dashboard.remove_style_class("hide")
                self.remove_style_class("launcher-contract")

                self.stack.set_visible_child(self.dashboard)

if __name__ == "__main__":
    notch = Notch()
    bar = DockBar()
    notch.set_role("notch")
    bar.notch = notch
    pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
    pill_size_group.add_widget(bar.pill)
    pill_size_group.add_widget(notch.stack)
    notch.stack
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