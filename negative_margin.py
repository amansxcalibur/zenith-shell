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
from fabric.widgets.revealer import Revealer
from systray import SystemTray
from fabric.widgets.datetime import DateTime
from workspaces import Workspaces, ActiveWindow
from metrics import MetricsSmall, Battery
from fabric.utils.helpers import exec_shell_command_async
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
            layer="top",
            geometry="top",
            type_hint="dock",
            margin="-4px -4px -8px -4px",
            visible=True,
            all_visible=True,
            **kwargs
        )

        self.notch = kwargs.get("notch", None)
        self.workspaces = Workspaces()
        self.systray = SystemTray()
        self.date_time = DateTime(name="date-time", formatters=["%H:%M"], h_align="center", v_align="center", h_expand=True, v_expand=True)

        self.metrics = MetricsSmall()
        self.battery = Battery()

        self.bar_inner = CenterBox(
            name="bar-inner",
            orientation="h",
            h_align="fill",
            v_align="center",
            start_children=Box(
                name="start-container",
                spacing=4,
                orientation="h",
                children=[
                    # self.button_apps,
                    self.workspaces
                ]
            ),
            end_children=Box(
                name="end-container",
                # spacing=4,
                orientation="h",
                children=[
                    self.systray,
                    self.metrics,
                    self.battery,
                    self.date_time,
                ],
            ),
        )
        self.systray._update_visibility()

        self.children = self.bar_inner
        self.hidden = False
        # self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        # self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

class Notch(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notch",
            layer="top",
            geometry="top",
            # margin="-8px -4px -8px -4px",
            # keyboard_mode="auto",
            type_hint="normal",
            # focusable=False
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self.launcher = AppLauncher(notch = self)
        # self.vol_slider = VolumeSlider(notch = self),
        self.volume_revealer = Revealer(
                    # name="metrics-cpu-revealer",
                    transition_duration=250,
                    transition_type="slide-down",
                    child=VolumeSlider(notch = self),
                    child_revealed=False,
                )
        self.vol_small = VolumeSmall(notch = self, slider_instance=self.volume_revealer)
        self.brightness = BrightnessSmall(device="intel_backlight")
        self.switch = True
        self.wall = WallpaperSelector()

        self.active_window = ActiveWindow()
        self.active_window.active_window.add_style_class("hide")
        self.user = Label(label="aman@brewery", name="user-label")
        self.dot_placeholder = Label(label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", name="collapsed-bar")

        self.notch_compact = Stack(
            name="collapsed",
            transition_type="slide-down",
            transition_duration=100,
            children=[
                self.user,
                self.active_window.active_window,
                self.dot_placeholder
            ]
        )
        self.notch_compact.set_visible_child(self.dot_placeholder)

        # EventBox with click event for toggling visibility
        self.collapsed = Gtk.EventBox(name="notch-compact")
        self.collapsed.set_visible(True)
        self.collapsed.add(self.notch_compact)

        self.collapsed.connect("button-press-event", self.toggle_collapse_child)

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

        # self.workspaces = Workspaces()
        # self.active_window
        
        self.children = Box(
            orientation="v",
            children=[
                CenterBox(
                    # start_children=[
                    #     self.workspaces,
                    # ],
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
                        ),
                    ],
                ),
                self.volume_revealer,
            ]
        )
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    # def toggle_name(self, *_):
    #     if self.collapsed.get_label()=="aman@brewery":
    #         return ". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . ."
    #     else:
    #         return "aman@brewery"

    def toggle_collapse_child(self, *_):
        if self.notch_compact.get_visible_child() == self.user:
            self.active_window.active_window.remove_style_class("hide")
            self.notch_compact.set_visible_child(self.active_window.active_window)
        elif self.notch_compact.get_visible_child() == self.active_window.active_window:
            self.active_window.active_window.add_style_class("hide")
            self.notch_compact.set_visible_child(self.dot_placeholder)
        else:
            self.notch_compact.set_visible_child(self.user)

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
    bar = Notch()
    dockBar = DockBar()
    dockBar.notch = bar
    # dockApp = Application('placeholder-dock', dockBar)
    app = Application("bar-example", bar, dockBar)
    # import builtins
    # builtins.bar = bar
    # FASS-based CSS file
    
    app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))    
    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()