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
            i3.command("gaps left all set 44px")
            i3.command("gaps top all set 3px")
        else:
            i3.command("gaps left all set 3px")
            i3.command("gaps top all set 0px")

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

class Notch(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="notch",
            layer="top",
            geometry="top" if not info.VERTICAL else "left",
            # margin="-8px -4px -8px -4px",
            # keyboard_mode="auto",
            type_hint="normal",
            # focusable=False
            margin="-8px -4px -8px -4px",
            visible=True,
            all_visible=True,
        )
        self.launcher = AppLauncher(notch = self)

        volume_slider = VolumeSlider(notch = self)
        volume_overflow_slider = VolumeSlider(notch = self)
        volume_overflow_slider.add_style_class("vol-overflow-slider")

        self.volume_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_slider,
                    child_revealed=False,
                )
        
        self.volume_overflow_revealer = Revealer(
                    transition_duration=250,
                    transition_type="slide-down" if not info.VERTICAL else "slide-right",
                    child=volume_overflow_slider,
                    child_revealed=False,
                )
        
        self.vol_small = VolumeSmall(notch = self, slider_instance=self.volume_revealer, overflow_instance = self.volume_overflow_revealer)

        self.brightness_revealer = Revealer(
            name="brightness",
            transition_duration=250,
            transition_type="slide-down" if not info.VERTICAL else "slide-right",
            child=BrightnessSlider(),
            child_revealed=True
        )
        self.brightness = BrightnessSmall(device="intel_backlight", slider_instance=self.brightness_revealer)
        
        self.switch = True
        self.wallpapers = WallpaperSelector(notch = self)

        self.player = PlayerContainer()
        self.player.add_style_class("hide-player")

        self.active_window = ActiveWindow()
        self.active_window.active_window.add_style_class("hide")
        self.user = Label(label="aman@brewery" if not info.VERTICAL else "am\nan\n@\nbr\new\ner\ny", name="user-label")
        self.dot_placeholder = Label(label=". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .", name="collapsed-bar") if not info.VERTICAL else Label(label="~", name="collapsed-bar", style_classes="vertical")

        self.notch_compact = Stack(
            name="collapsed",
            transition_type="crossfade",
            transition_duration=100,
            style_classes="" if not info.VERTICAL else "vertical",
            children=[
                self.user,
                self.active_window.active_window,
                self.dot_placeholder,
            ]
        )
        self.notch_compact.set_visible_child(self.dot_placeholder)

        # EventBox with click event for toggling visibility
        self.collapsed = Gtk.EventBox(name="notch-compact")
        self.collapsed.set_visible(True)
        self.collapsed.add(self.notch_compact)

        self.collapsed.connect("button-press-event", self.toggle_collapse_child)

        self.expanding = self.launcher

        if info.VERTICAL:
            self.expanding.add_style_class("vertical")
            self.wallpapers.add_style_class("vertical")
            self.player.add_style_class("vertical")
        else:
            self.launcher.add_style_class("launcher-contract-init")
            self.wallpapers.add_style_class("wallpaper-contract")
        
        self.stack = Stack(
            name="notch-content",
            h_expand=True, 
            v_expand=True,
            transition_type="crossfade", 
            transition_duration=250,
            style_classes="" if not info.VERTICAL else "vertical",
            children=[
                self.collapsed,
                self.expanding,
                self.wallpapers,
                self.player
            ])

        self.stack.set_visible_child(self.collapsed)
        self.add_keybinding("Escape", lambda *_: self.close())

        self.full_notch = Box(
            orientation="v" if not info.VERTICAL else "h",
            children=[
                CenterBox(
                    orientation='h' if not info.VERTICAL else 'v',
                    center_children=[
                        CenterBox(
                            label="L",
                            name="left",
                            h_align="start",
                            v_align="start",
                            style_classes="" if not info.VERTICAL else "verticals",
                            center_children=[Box(label="L", name="left-dum", children=[self.brightness], v_expand=False)],
                            v_expand=False
                        ),
                        self.stack,
                        CenterBox(
                            label="R",
                            name="right",
                            h_align="start",
                            v_align="start",
                            style_classes="" if not info.VERTICAL else "verticals",
                            center_children=[Box(label="R", name="right-dum",children=[self.vol_small], v_expand=False)],
                            v_expand=False
                        ),
                    ],
                ),
                self.volume_revealer,
                self.volume_overflow_revealer,
                self.brightness_revealer
            ]
        )
        self.hidden_notch = Box()
        self.visibility_stack = Stack(
            transition_type="over-down", 
            transition_duration=100,
            children=[
                self.full_notch,
                self.hidden_notch
            ]
        )

        self.children = self.visibility_stack
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

    def toggle_player(self, *_):
        if self.stack.get_visible_child() != self.player:
            exec_shell_command_async('i3-msg [class="Negative_margin.py"] focus')
            if info.VERTICAL:
                self.player.remove_style_class("vertical")
            else:    
                self.player.remove_style_class("hide-player")
            self.player.add_style_class("reveal-player")
            self.stack.set_visible_child(self.player)
        else:
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            else:
                self.player.add_style_class("hide-player")
            self.stack.set_visible_child(self.collapsed)

    def open(self, *_):
        if self.visibility_stack.get_visible_child() == self.full_notch:
            # self.steal_input()
            exec_shell_command_async('i3-msg [window_role="notch"] focus')
            if self.stack.get_visible_child() == self.collapsed:
                print("opeing")
                # self.stack.remove_style_class("contract")
                # self.stack.add_style_class("expand")
                # # self.remove_style_class("wallpaper-init")
                # self.remove_style_class("launcher-contract-init")
                if info.VERTICAL:
                    self.launcher.remove_style_class("vertical")
                else:
                    self.launcher.remove_style_class("launcher-contract")
                self.launcher.add_style_class("launcher-expand")
                self.stack.set_visible_child(self.expanding)
                
                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()

            elif self.stack.get_visible_child() == self.player:
                if info.VERTICAL:
                    self.player.remove_style_class("vertical")
                else:
                    self.player.remove_style_class("reveal-player")
                # self.player.add_style_class("hide-player")
                if info.VERTICAL:
                    self.launcher.remove_style_class("vertical")
                else:
                    self.launcher.remove_style_class("launcher-contract")
                self.launcher.add_style_class("launcher-expand")
                self.stack.set_visible_child(self.expanding)
                
                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()
        else:
            print("Notch is hidden")
        self.show_all()
    
    def close(self, *_):
        if self.stack.get_visible_child() == self.player:
            self.player.remove_style_class("reveal-player")
            if info.VERTICAL:
                self.player.add_style_class("vertical")
            else:
                self.player.add_style_class("hide-player")
            
            self.stack.set_visible_child(self.collapsed)

        elif self.stack.get_visible_child() != self.collapsed:
            self.stack.remove_style_class("expand")
            
            # self.unsteal_input()
            self.wallpapers.remove_style_class("wallpaper-expand")
            if info.VERTICAL:
                self.wallpapers.add_style_class("vertical")
            else:
                self.wallpapers.add_style_class("wallpaper-contract")

            self.stack.add_style_class("contract")

            self.launcher.remove_style_class("launcher-expand")
            if info.VERTICAL:
                self.launcher.add_style_class("vertical")
            else:
                self.launcher.add_style_class("launcher-contract")
            self.stack.set_visible_child(self.collapsed)
            exec_shell_command_async(f'i3-msg focus mode_toggle')
            # self.launcher.close_launcher()
         
        # for cases where player->dmenu->close()
        if info.VERTICAL:
            self.player.add_style_class("vertical")
        else:
            self.player.add_style_class("hide-player")
        self.show_all()

    def open_notch(self, *_):
        self.remove_style_class("launcher-contract")
        # if info.VERTICAL:
        self.wallpapers.remove_style_class("vertical")
        # else:
        self.wallpapers.remove_style_class("wallpaper-contract")
        self.wallpapers.remove_style_class("wallpaper-init")
        self.wallpapers.add_style_class("wallpaper-expand")
        self.stack.set_visible_child(self.wallpapers)

if __name__ == "__main__":
    bar = Notch()
    dockBar = DockBar()
    bar.set_role("notch")
    dockBar.notch = bar
    if info.VERTICAL:
        # make the window consume all vertical space
        monitor = dockBar._display.get_primary_monitor()
        rect = monitor.get_geometry()
        scale = monitor.get_scale_factor()
        dockBar.set_size_request(0, rect.height * scale)
        dockBar.show_all()

    app = Application("bar-example", bar, dockBar, open_inspector=False)
    # import builtins
    # builtins.bar = bar
    # FASS-based CSS file
    

    app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))     
    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()