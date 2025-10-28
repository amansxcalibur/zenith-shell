from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.overlay import Overlay


import config.info as info
import icons
from utils.helpers import toggle_class

import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

SPACING = 0


class NotificationBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry="top",
            type_hint="notification",
            margin="0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )

        self.build_bar()

        self.add_keybinding("Escape", lambda *_: self.close())

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

    def build_bar(self):
        self.reveal_btn = Button(
            name="notification-reveal-btn",
            child=Label(name="notification-reveal-label", markup=icons.notifications),
            tooltip_text="Show/Hide notifications",
            # on_clicked=lambda *_: self.toggle_notification_stack_reveal(),
            visible=True,
        )
        self.clear_btn = Button(
            name="notification-reveal-btn",
            child=Label(name="notification-clear-label", markup=icons.trash),
            tooltip_text="Show/Hide notifications",
            # on_clicked=lambda *_: self.close_all_notifications(),
            visible=True,
        )

        self.left_pill_curve = Box(name="start-notif-controls", h_expand=True)
        self.right_pill_curve = Box(name="end-notif-controls", h_expand=True)

        self.start_children = Box(
            children=[
                Box(name="start-notif-control-left-drop"),
                Overlay(
                    h_expand=True,
                    child=self.left_pill_curve,
                    overlays=Box(
                        spacing=10,
                        children=[
                            self.clear_btn,
                            # Label(markup = icons.alien)
                        ],
                    ),
                ),
            ],
            h_expand=True,
        )
        self.end_children = Box(
            children=[
                Overlay(
                    h_expand=True,
                    child=self.right_pill_curve,
                    overlays=Box(
                        spacing=10,
                        children=[self.reveal_btn, 
                                #   Label(markup=icons.trisquel)
                                ],
                    ),
                ),
                Box(name="end-notif-control-left-drop"),
            ]
        )

        self.pill = Box(name="vert-notif")

        self.pill_container = Box(
            children=[
                self.left_pill_curve,
                Box(
                    name="hori-notif",
                    style_classes="pill",
                    orientation="v",
                    children=[Box(name="bottom", v_expand=True), self.pill],
                ),
                self.right_pill_curve,
            ]
        )

        self.children = Box(
            name="main-notif",
            children=[self.start_children, self.pill_container, self.end_children],
        )

        # size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        # size_group.add_widget(self.start_children)
        # size_group.add_widget(self.end_children)
