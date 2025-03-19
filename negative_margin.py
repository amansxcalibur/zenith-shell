import fabric
from fabric import Application
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.utils import get_relative_path
from fabric.widgets.x11 import X11Window as Window
from launcher import AppLauncher
from corner import Corners, MyCorner
from fabric.utils.helpers import exec_shell_command_async
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk
from wallpaper import WallpaperSelector
from volume import VolumeSlider, VolumeSmall
from brightness import BrightnessSmall

class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="status-bar",
            layer="overlay",
            geometry="top",
            type_hint="dock",
            **kwargs
        )
        self.children = Box(
            name="placeholder",
            orientation="v",
            children=[
                CenterBox(
                    center_children=[
                        Label(label="aman@brewery", name="middle"),
                    ],
                ),
            ],
        )
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

class StatusBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            layer="top",
            geometry="top",
            # margin="-8px -4px -8px -4px",
            # keyboard_mode="auto",,
            # type="popup"
            type_hint="notification",
            # focusable=False
        )
        # self.set_name("status-bar")
        self.launcher = AppLauncher(notch = self)
        self.volume = VolumeSlider(notch = self)
        self.vol_small = VolumeSmall(notch = self)
        self.brightness = BrightnessSmall(device="intel_backlight")
        self.switch = True
        self.wall = WallpaperSelector()
        
        self.collapsed = Button(
            label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", 
            name="collapsed-bar", 
            on_clicked=lambda b, *_:b.set_label(self.toggle_name(b))
            )
        
        # self.expanding = Box(
        #     children=[
        #         # Button(label="Collapse", name="expanding-bar", on_clicked=self.toggle),
        #         self.launcher,
        #         # Button(label="Collapse", name="expanding-bar", on_clicked=self.toggle),
        #         ])

        self.expanding = self.launcher
        
        self.stack = Stack(
            name="notch-content",
            h_expand=True, 
            v_expand=True, 
            transition_type="crossfade", 
            transition_duration=100,
            children=[
                self.expanding,
                self.collapsed,
                self.wall
            ])
        
        self.launcher.add_style_class("launcher-contract-init")
        self.wall.add_style_class("wallpaper-contract")

        self.stack.set_visible_child(self.collapsed)
        self.add_keybinding("Escape", lambda *_: self.close())
        self.children = Box(
            orientation="v",
            children=[
                CenterBox(
                    center_children=[
                        CenterBox(
                            label="L",
                            name="left",
                            v_align="start",
                            center_children=[Box(label="L", name="left-dum", children=[self.brightness], v_expand=False)],
                            v_expand=False
                        ),
                        self.stack,
                        CenterBox(
                            label="R",
                            name="right",
                            v_align="start",
                            center_children=[Box(label="R", name="right-dum",children=[self.vol_small], v_expand=False)],
                            v_expand=False
                        )
                    ],
                ),
                # self.volume,
            ]
        )
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    def toggle_name(self, *_):
        if self.collapsed.get_label()=="aman@brewery":
            return ". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . ."
        else:
            return "aman@brewery"

    def open(self, *_):
        if self.stack.get_visible_child() == self.collapsed:
            # self.steal_input()
            self.stack.remove_style_class("contract")
            self.stack.add_style_class("expand")
            self.remove_style_class("wallpaper-init")
            self.remove_style_class("launcher-contract-init")
            self.launcher.remove_style_class("launcher-contract")
            self.launcher.add_style_class("launcher-expand")
            self.stack.set_visible_child(self.expanding)
            
            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()
        self.show_all()
    
    def close(self, *_):
        if self.stack.get_visible_child() != self.collapsed:
            self.stack.remove_style_class("expand")
            self.stack.add_style_class("contract")
            # self.unsteal_input()
            self.wall.remove_style_class("wallpaper-expand")
            self.wall.add_style_class("wallpaper-contract")
            self.launcher.remove_style_class("launcher-expand")
            self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.collapsed)
            exec_shell_command_async(f'i3-msg focus mode_toggle')
            # self.launcher.close_launcher()
        self.show_all()

    def open_notch(self, *_):
        self.remove_style_class("launcher-contract")
        self.wall.remove_style_class("wallpaper-init")
        self.wall.add_style_class("wallpaper-expand")
        # self.stack.add(self.wall)
        self.stack.set_visible_child(self.wall)

if __name__ == "__main__":
    bar = StatusBar()
    # dockBar = DockBar()
    # dockApp = Application('placeholder-dock', dockBar)
    app = Application("bar-example", bar)
    # import builtins
    # builtins.bar = bar
    # FASS-based CSS file
    
    app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))    
    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()