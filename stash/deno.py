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
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk

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
            anchor="left top right",
            # margin="-8px -4px -8px -4px",
            exclusivity="auto",
            visible=True,
            all_visible=True,
            # type="popup"
            type_hint="normal"
        )
        self.set_name("status-bar")
        self.launcher = AppLauncher()
        self.switch = True
        
        self.collapsed = Button(label="Expand", name="collapsed-bar", on_clicked=self.toggle)
        
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
                # self.expanding,
                self.collapsed
            ])

        # self.stack.add_named(self.collapsed, "collapsed")
        # self.stack.add_named(self.expanding, "expanded")
        # self.stack.add_named(self.expanding, "expanded")
        self.stack.set_visible_child(self.collapsed)
        self.add_keybinding("Escape", lambda *_: self.toggle())
        self.children = Box(
            orientation="v",
            children=[
                CenterBox(
                    center_children=[
                        CenterBox(
                            label="L",
                            name="left",
                            v_align="start",
                            center_children=[Label(label="L", name="left-dum", v_expand=False)],
                            v_expand=False
                        ),
                        self.stack,
                        CenterBox(
                            label="R",
                            name="right",
                            v_align="start",
                            center_children=[Label(label="R", name="right-dum", v_expand=False)],
                            v_expand=False
                        )
                    ],
                ),
            ]
        )
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])
    
    def after_transition(self):
            self.stack.add_named(self.expanding, "expanded")
            self.stack.set_visible_child(self.expanding)
            self.launcher.open_launcher()
            self.launcher.search_entry.set_text("")
            self.launcher.search_entry.grab_focus()

    def toggle(self, *_):
        if self.switch:
            self.switch = not self.switch
            self.stack.remove_style_class("contract")
            self.stack.add_style_class("expand")
            GLib.timeout_add(500, self.after_transition)
            
        else:
            self.switch = not self.switch
            self.stack.set_visible_child(self.collapsed)
            self.stack.remove_style_class("expand")
            self.stack.add_style_class("contract")

            self.stack.remove(self.expanding)
            self.launcher.close_launcher()
        # if self.stack.get_visible_child() == self.collapsed:
        #     # self.collapsed.remove_style_class("collapsed")
        #     # self.collapsed.add_style_class("expand")
        #     # self.expanding.add_style_class("expand")
        #     # self.stack.add_named(self.expanding, "expanded")
        #     self.stack.set_visible_child(self.expanding)
        #     self.stack.add_style_class("expand")
        #     # self.expanding.add_style_class("expand")
        #     # self.launcher.open_launcher()
        #     # self.launcher.search_entry.set_text("")
        #     # self.launcher.search_entry.grab_focus()
        # else:
        #     self.stack.remove_style_class("expand")
        #     # self.stack.remove(self.expanding)
        #     self.stack.set_visible_child(self.collapsed)
        #     # self.expanding.remove_style_class("expand")
        #     # self.launcher.close_launcher()
        #     # self.stack.set_visible_child(self.collapsed)
        self.show_all()

if __name__ == "__main__":
    bar = StatusBar()
    dockBar = DockBar()
    dockApp = Application('placeholder-dock', dockBar)
    app = Application("bar-exampled", bar)

    # FASS-based CSS file
    app.set_stylesheet_from_file(get_relative_path("./styles/dynamic.css"))

    app.run()