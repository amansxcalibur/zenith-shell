import fabric
from fabric import Application
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.revealer import Revealer
from fabric.utils import get_relative_path
from fabric.widgets.x11 import X11Window as Window

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
            name="status-bar",
            layer="overlay",
            geometry="top",
            type_hint="notification",
            **kwargs
        )
        self.set_name("status-bar")

        # Revealer for expanded and collapsed states
        self.revealer_box = Box(orientation="v")  # Keeps revealers in the same place
        self.expand = Revealer(
            child=Button(label="Expand", name="collapsed-bar", on_clicked=self.toggle),
            child_revealed=True,  # Initially visible
            transition_type="crossfade",
            transition_duration=300
        )
        self.collapse = Revealer(
            child=Button(label="Collapse", name="expanding-bar", on_clicked=self.toggle),
            child_revealed=False,  # Initially hidden
            transition_type="crossfade",
            transition_duration=300,
        )

        self.revealer_box.children = [self.expand, self.collapse]

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
                        self.revealer_box,
                        CenterBox(
                            label="R",
                            name="right",
                            v_align="start",
                            center_children=[Label(label="R", name="right-dum", v_expand=False)],
                            v_expand=False
                        )
                    ],
                )
            ],
        )
        
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])

    def toggle(self, *_):
        self.expand.child_revealed = not self.expand.child_revealed
        self.collapse.child_revealed = not self.collapse.child_revealed

if __name__ == "__main__":
    bar = StatusBar()
    dockBar = DockBar()
    dockApp = Application('placeholder-dock', dockBar)
    app = Application("bar-example", bar)

    # FASS-based CSS file
    app.set_stylesheet_from_file(get_relative_path("./styles/main.css"))

    app.run()
