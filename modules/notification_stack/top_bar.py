from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.x11 import X11Window as Window

from widgets.clipping_box import ClippingBox

import icons
from config.info import config
from utils.helpers import toggle_class
from utils.cursor import add_hover_cursor

import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

SPACING = 0


class TopBar(Window):
    def __init__(self, pill, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry="top",
            type_hint="normal",
            margin="0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )
        self._pill_ref = pill

        self.is_open = False
        self._pill_is_docked = True

        self.hole_state_left = False
        self.hole_state_right = False

        self.init_modules()
        self.build_bar()

        self.add_keybinding("Escape", lambda *_: self.close())

    def init_modules(self):
        self.reveal_btn = Button(
            # name="notification-reveal-btn",
            child=Label(name="notification-reveal-label", markup=icons.notifications),
            tooltip_text="Show/Hide notifications",
            on_clicked=lambda *_: (
                ... if True else self.toggle_notification_stack_reveal()
            ),
            # visible=False,
        )
        self.clear_btn = Button(
            # name="notification-reveal-btn",
            child=Label(name="notification-clear-label", markup=icons.trash),
            tooltip_text="Show/Hide notifications",
            on_clicked=lambda *_: ... if True else self.close_all_notifications(),
            # visible=False,
        )

        self.user_modules_left = [
            self.clear_btn,
        ]
        self.user_modules_right = [
            self.reveal_btn,
        ]

    def build_bar(self):
        self.left_compact = Box(
            style="min-width:1px; min-height:1px; background-color:black"
        )
        self.left_child = Label(label="helo")
        self.left = Stack(
            transition_duration=300,
            transition_type="over-down",
            children=[self.left_compact, self.left_child],
        )
        self.left.set_interpolate_size(True)
        self.left.set_homogeneous(False)

        self.right_compact = Box(
            style="min-width:1px; min-height:1px; background-color:black"
        )
        self.right_child = Label(label="helo")
        self.right = Stack(
            transition_duration=300,
            transition_type="over-down",
            children=[self.right_compact, self.right_child],
        )
        self.right.set_interpolate_size(True)
        self.right.set_homogeneous(False)

        self.start_children = Box(
            name="start-top",
            h_expand=True,
            children=self.left,
        )
        self.end_children = Box(
            name="end-top",
            h_expand=True,
            children=self.right,
        )
        self.left_edge = Box(name="left-edge", h_expand=True)
        self.right_edge = Box(name="right-edge", h_expand=True)

        self.pill_dock = Box(name="vert-top")
        self.pill_dock_container = Box(
            children=[
                Box(
                    name="hori-top",
                    style_classes="pill",
                    orientation="v",
                    children=[Box(name="bottom-top", v_expand=True), self.pill_dock],
                ),
            ]
        )
        self.compact = Box(
            style="min-width:1px; min-height:1px; background-color:black"
        )
        self.stack = Stack(
            transition_duration=300,
            transition_type="over-up",
            children=[self.pill_dock_container, self.compact],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = Box(
            name="top-main",
            children=[
                self.left_edge,
                self.start_children,
                self.stack,
                self.end_children,
                self.right_edge,
            ],
        )

    def get_is_open(self):
        return self.is_open

    def set_pill_docked(self, docked: bool):
        self._pill_is_docked = docked

    def override_close(self):
        self._pill_is_docked = False
        self.stack.set_visible_child(self.compact)
        self._apply_close_visual()

    def override_reset(self):
        self._pill_is_docked = True
        self.stack.set_visible_child(self.pill_dock_container)
        # print("top bar is ", self.is_open)
        if self.is_open:
            self._apply_open_visual()
        else:
            self._apply_close_visual()

    def open(self):
        self.is_open = True
        if self._pill_is_docked:
            self._apply_open_visual()

    def close(self):
        self.is_open = False
        if self._pill_is_docked:
            self._apply_close_visual()

    def _apply_open_visual(self):
        print("opening")
        self.left.set_visible_child(self.left_child)
        self.right.set_visible_child(self.right_child)
        toggle_class(self.pill_dock, "contractor", "expand")
        toggle_class(self.pill_dock_container, "contractor", "expander")
        # toggle_class(self.left_end_pill_curve, "contractor", "expander")
        # toggle_class(self.right_start_pill_curve, "contractor", "expander")
        # toggle_class(self.left_start_pill_curve, "contractor", "expander")
        # toggle_class(self.right_end_pill_curve, "contractor", "expander")

    def _apply_close_visual(self):
        print("closing")
        self.left.set_visible_child(self.left_compact)
        self.right.set_visible_child(self.right_compact)
        toggle_class(self.pill_dock, "expand", "contractor")
        toggle_class(self.pill_dock_container, "expander", "contractor")
        # toggle_class(self.left_end_pill_curve, "expander", "contractor")
        # toggle_class(self.right_start_pill_curve, "expander", "contractor")
        # toggle_class(self.left_start_pill_curve, "expander", "contractor")
        # toggle_class(self.right_end_pill_curve, "expander", "contractor")

    def toggle_vertical(self):
        # toggle_config_vertical_flag()
        # restart bar
        subprocess.run([f"{config.SCRIPTS_DIR}/flaunch.sh"])

    def toggle_visibility(self):
        visible = not self.is_visible()
        self.set_visible(visible)
        self._pill_ref._dock_is_visible = visible

    def close_bar(self): ...
