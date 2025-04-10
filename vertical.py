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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk
from wallpaper import WallpaperSelector
from volume import VolumeSlider, VolumeSmall
from brightness import BrightnessSlider, BrightnessSmall

class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="status-bar",
            layer="top",
            geometry="top" if not info.VERTICAL else "left",
            type_hint="normal" if info.VERTICAL else "dock",
            margin="0px 0px 0px 0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs
        )

        print("-----------------------here is vertical status-----------------------\n", info.VERTICAL)


        i3 = Connection()
        if info.VERTICAL:
            i3.command("gaps left all set 42px")
            i3.command("gaps top all set 3px")
        else:
            i3.command("gaps left all set 3px")

        # self.children = Box(
        #     name="vertical-bar",
        #     orientation='v',
        #     children=Label(label="hello vertical")
        # )

        self.notch = kwargs.get("notch", None)
        self.workspaces = Workspaces()
        self.systray = SystemTray()
        self.date_time = Box(
            name="date-time-container", 
            style_classes="" if not info.VERTICAL else "vertical" ,
            children=DateTime(
                name="date-time", 
                formatters=["%H\n%M"] if info.VERTICAL else ["%H:%M"], 
                h_align="center", 
                v_align="center", 
                h_expand=True, 
                v_expand=True ,
                style_classes="" if not info.VERTICAL else "vertical"
            )
        )

        self.metrics = MetricsSmall()
        self.battery = Battery()

        self.bar_inner = CenterBox(
            name="bar-inner",
            orientation="h" if not info.VERTICAL else "v",
            h_align="fill" if not info.VERTICAL else "center", 
            v_align="center" if not info.VERTICAL else "fill", 
            start_children=Box(
                name="start-container",
                spacing=4,
                orientation="h" if not info.VERTICAL else "v",
                # v_align="center",
                children=[
                    # Button(name="hide-bar-toggle", on_clicked=lambda b: self.hide_bar_toggle()),
                    self.workspaces
                ]
            ),
            end_children=Box(
                name="end-container",
                # spacing=4,
                orientation="h" if not info.VERTICAL else "v",
                children=[
                    self.systray,
                    self.metrics,
                    self.battery,
                    self.date_time,
                ],
            ),
        )
        self.systray._update_visibility()

        self.hidden_bar = Box()
        self.visibility_stack = Stack(
            h_expand=True,
            v_expand=True,
            transition_type="over-down", 
            transition_duration=100,
            children=[self.bar_inner,self.hidden_bar]
        )
        self.children = self.visibility_stack
        self.hidden = False
        # self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        # self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    def hide_bar_toggle(self):
        # this function runs through i3 keybindings
        if self.visibility_stack.get_visible_child() == self.bar_inner:
            # self.bar_inner.remove_style_class("reveal-bar")
            self.bar_inner.add_style_class("hide-bar")            
            self.notch.full_notch.add_style_class("hide-notch")

            self.visibility_stack.set_visible_child(self.hidden_bar)
            self.notch.visibility_stack.set_visible_child(self.notch.hidden_notch)
        else:
            # self.bar_inner.add_style_class("reveal-bar")
            self.bar_inner.remove_style_class("hide-bar")
            self.notch.full_notch.remove_style_class("hide-notch")
            
            self.visibility_stack.set_visible_child(self.bar_inner)
            self.notch.visibility_stack.set_visible_child(self.notch.full_notch)

if __name__ == "__main__":
    dockBar = DockBar()
    if info.VERTICAL:
        # make the window consume all vertical space
        monitor = dockBar._display.get_primary_monitor()
        rect = monitor.get_geometry()
        scale = monitor.get_scale_factor()
        dockBar.set_size_request(0, rect.height * scale)
        dockBar.show_all()

    app = Application("bar-example", dockBar, open_inspector=True)
    # import builtins
    # builtins.bar = bar
    # FASS-based CSS file
    

    app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))     
    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()