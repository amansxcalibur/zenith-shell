import time

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.x11 import X11Window as Window

import icons
from config.info import config
from utils.helpers import toggle_class
from utils.cursor import add_hover_cursor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

SPACING = 0
CONTROLS_SPACING = 5


class TopBar(Window):
    def __init__(self, pill, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="top",
            geometry="top",
            type_hint="notification",
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

        self._cleanup_controls = None
        self._boxes_to_clean = []

        self.last_hover_time = 0

        self.init_modules()
        self.build_bar()

        self._pill_ref.connect("child-changed", self.update_controls)

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
        self.left_child = Box(spacing=SPACING)  # Changed from Label
        self.left = Stack(
            transition_duration=300,
            transition_type="crossfade",
            children=[self.left_compact, self.left_child],
        )
        self.left.set_interpolate_size(True)
        self.left.set_homogeneous(False)

        self.right_compact = Box(
            style="min-width:1px; min-height:1px; background-color:black"
        )
        self.right_child = Box(spacing=SPACING)  # Changed from Label
        self.right = Stack(
            transition_duration=300,
            transition_type="crossfade",
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

        self.hover_area = EventBox(
            events="enter-notify",
            h_expand=True, 
            child=Box(style="min-height:2px;"), # width defined in top-main
        )

        self.children = Overlay(
            orientation="v",
            overlays=Box(v_align="start", v_expand=False, h_expand=True, children=self.hover_area),
            child=Box(
                name="top-main",
                children=[
                    self.left_edge,
                    self.start_children,
                    self.stack,
                    self.end_children,
                    self.right_edge,
                ],
            ),
        )

        self.hover_area.connect("enter-notify-event", self._handle_hover_reveal)

    def _handle_hover_reveal(self, source, event):
        if (
            event.detail == Gdk.NotifyType.INFERIOR
        ):  # hovering to a child widget, don't toggle
            return

        now = time.time()
        if now - self.last_hover_time < 0.3:
            return  # ignore rapid flickers
        self.last_hover_time = now

        self._pill_ref.toggle_notification()

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

    def _apply_close_visual(self):
        print("closing")
        self.left.set_visible_child(self.left_compact)
        self.right.set_visible_child(self.right_compact)
        toggle_class(self.pill_dock, "expand", "contractor")
        toggle_class(self.pill_dock_container, "expander", "contractor")

    def toggle_vertical(self):
        # toggle_config_vertical_flag()
        # restart bar
        ...

    def toggle_visibility(self):
        visible = not self.is_visible()
        self.set_visible(visible)
        self._pill_ref._dock_is_visible = visible

    def bake_bar_buttons(self, widget):
        widget.add_style_class("top-bar-control-btn")
        return add_hover_cursor(widget=widget)

    def update_controls(self, source, child_controls):
        print("update controls", child_controls)

        # 3. Identify the OLD children (which are the current "content" children)
        old_left = self.left_child
        old_right = self.right_child

        # --- NEW STEP: 0. IMMEDIATE RESCUE OF PERSISTENT CONTROLS ---
        # Before creating new containers, we must unparent the controls
        # from the containers they currently reside in (old_left/old_right).
        # This prevents reparenting issues.

        # Only rescue if the old containers are transient (i.e., not self.left_compact)
        protected = [self.left_compact, self.right_compact]

        if old_left not in protected:
            for child in old_left.get_children():
                old_left.remove(child)

        if old_right not in protected:
            for child in old_right.get_children():
                old_right.remove(child)

        # 1. Create new containers with unique names
        next_left = Box(
            name=f"left_ctrl_{GLib.get_monotonic_time()}",
            style_classes=["top-bar-controls-box"],
            spacing=CONTROLS_SPACING,
        )
        next_right = Box(
            name=f"right_ctrl_{GLib.get_monotonic_time()}",
            style_classes=["top-bar-controls-box"],
            spacing=CONTROLS_SPACING,
        )

        # Populate them
        if not child_controls:
            next_left.add(Label(label="empty"))
            next_right.add(Label(label="empty"))
        else:
            # Controls are now unparented and safe to add to the new boxes
            for index, control in enumerate(child_controls):
                if index % 2 == 0:
                    next_left.add(self.bake_bar_buttons(control))
                else:
                    next_right.add(self.bake_bar_buttons(control))

        # 2. Add new containers to the Stacks
        self.left.add(next_left)
        self.right.add(next_right)

        # --- NEW STEP: 3. TRACK OLD BOXES FOR LATER DESTRUCTION ---
        # Add the now-empty old containers to the list for eventual cleanup.
        # This tracks every container that needs removal.
        if old_left not in protected:
            self._boxes_to_clean.append(old_left)
        if old_right not in protected:
            self._boxes_to_clean.append(old_right)

        # 4. Update the "Main" references
        self.left_child = next_left
        self.right_child = next_right

        # 5. Handle Visibility Logic (Remains unchanged)
        if self.is_open:
            self.left.set_visible_child(next_left)
            self.right.set_visible_child(next_right)

        self.show_all()

        # 6. Cleanup Logic (Run only if a cleanup isn't already scheduled)
        if self._cleanup_controls is not None:
            # Cleanup is already scheduled, just let it run on the updated list
            return

        def cleanup_scheduled_boxes():
            # Crucial: Reset the tracker
            self._cleanup_controls = None

            # Remove and destroy all accumulated transient containers
            for box in self._boxes_to_clean:
                # Check if the box is still in the stack before removing
                if box in self.left.get_children():
                    self.left.remove(box)
                elif box in self.right.get_children():
                    self.right.remove(box)

            # Clear the list after cleanup
            self._boxes_to_clean.clear()

            return False

        # Schedule the new cleanup and store the source ID
        self._cleanup_controls = GLib.timeout_add(350, cleanup_scheduled_boxes)

    def tester(self):
        label = Label(label="minansan konichiwa")
        self.left.add_named(label, "silly")
        self.left.set_visible_child(label)

    def set_unique_name(self, widget, prefix):
        widget.set_name(f"{prefix}_{GLib.get_monotonic_time()}")
