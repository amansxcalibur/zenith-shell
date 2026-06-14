import time
from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.x11 import X11WindowGeometry

from widgets.clipping_box import ClippingBox
from widgets.overrides import PatchedX11Window as Window
from utils.helpers import toggle_class
from utils.cursor import add_hover_cursor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

SPACING = 0
CONTROLS_SPACING = 5
TRANSITION_DURATION = 300
CLEANUP_DELAY = 350


class TopBar(Window):
    def __init__(self, pill, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="top",
            geometry="top",
            type_hint="notification",
            visible=True,
            all_visible=True,
            **kwargs,
        )
        self._pill_ref = pill

        self.is_open = False
        self._pill_is_docked = True
        self.detach_mode = False

        self._controls_visibility_timeout_id: int = None
        self._cleanup_timeout_id: int | None = None
        self._detach_animation_timeout_id: int | None = None
        self._detach_toggle_timeout_id: int | None = None
        self._detach_edge_timeout_id: int | None = None
        self._boxes_to_clean: list[Box] = []

        self.last_hover_time = 0

        self._controls_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)

        self.init_modules()
        self.build_bar()
        self.toggle_controls_visibility()

        self._pill_ref.connect("child-changed", self.update_controls)
        self.add_keybinding("Escape", lambda *_: self.close())

        self.connect("delete-event", self.on_delete_event)
        self.connect("destroy", self._on_destroy)

    def init_modules(self):
        # left
        self.left_compact = Box(style="min-width:1px; min-height:1px;")
        self.left_child = Box(spacing=SPACING)
        self.left = self._create_stack([self.left_compact, self.left_child])

        # right
        self.right_compact = Box(style="min-width:1px; min-height:1px;")
        self.right_child = Box(spacing=SPACING)
        self.right = self._create_stack([self.right_compact, self.right_child])

        self._protected_boxes = {self.left_compact, self.right_compact}

    def _create_stack(
        self,
        children: list,
        transition_type: str = "crossfade",
        name: str = "",
        style_classes: list = [],
    ) -> Stack:
        stack = Stack(
            name=name,
            style_classes=style_classes,
            transition_duration=TRANSITION_DURATION,
            transition_type=transition_type,
            children=children,
        )
        stack.set_interpolate_size(True)
        stack.set_homogeneous(False)
        return stack

    def build_bar(self):
        self.start_children = Box(name="start-top", h_expand=True, children=self.left)
        self.end_children = Box(name="end-top", h_expand=True, children=self.right)
        self.left_edge = Box(name="left-edge", h_expand=True)
        self.right_edge = Box(name="right-edge", h_expand=True)

        # Im too lazy to center the window based on pill
        self._controls_size_group.add_widget(self.start_children)
        self._controls_size_group.add_widget(self.end_children)

        # pill
        self.pill_dock = Box(name="vert-top")
        self.pill_vertical = Box(
            # name="hori-top",
            # style_classes="pill",
            orientation="v",
            children=[Box(name="bottom-top", v_expand=True), self.pill_dock],
        )
        self.pill_dock_container = Box(children=[self.pill_vertical])

        self.compact = Box(
            style="min-width:1px; min-height:1px; background-color:transparent"
        )
        self.stack = self._create_stack(
            children=[self.pill_dock_container, self.compact],
            transition_type="crossfade",
            name="hori-top",
            style_classes=["pill"],
        )

        # styles init
        self.toggle_detach(detach=False)

        # hover area
        self.hover_area = EventBox(
            events="enter-notify",
            h_expand=True,
            child=Box(style="min-height:2px; min-width:500px"),
        )
        self.hover_area.connect("enter-notify-event", self._handle_hover_reveal)

        # main
        self.children = Overlay(
            orientation="v",
            overlays=Box(
                v_align="start", v_expand=False, h_expand=True, children=self.hover_area
            ),
            child=Box(
                name="top-main",
                children=[
                    self.left_edge,
                    self.start_children,
                    # to prevent curved edges to overflow
                    ClippingBox(children=self.stack),
                    self.end_children,
                    self.right_edge,
                ],
            ),
        )

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
        if not self._pill_is_docked:
            return

        self._pill_is_docked = False
        self.stack.set_visible_child(self.compact)
        self._apply_close_visual()

    def override_reset(self):
        if self._pill_is_docked:
            return

        self._pill_is_docked = True
        self.stack.set_visible_child(self.pill_dock_container)

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
        self.left.set_visible_child(self.left_child)
        self.right.set_visible_child(self.right_child)
        toggle_class(self.pill_dock, "contractor", "expand")
        toggle_class(self.pill_dock_container, "contractor", "expander")

        if self.detach_mode:
            self.detach_controls(detach=True)
        else:
            self.detach_edge(detach=False)

        if self._controls_visibility_timeout_id:
            GLib.source_remove(self._controls_visibility_timeout_id)

        self.toggle_controls_visibility()

    def _apply_close_visual(self):
        self.left.set_visible_child(self.left_compact)
        self.right.set_visible_child(self.right_compact)
        toggle_class(self.pill_dock, "expand", "contractor")
        toggle_class(self.pill_dock_container, "expander", "contractor")

        if self.detach_mode:
            self.detach_controls(detach=False)
        else:
            self.detach_edge(detach=True)

        if self._controls_visibility_timeout_id:
            GLib.source_remove(self._controls_visibility_timeout_id)

        self._controls_visibility_timeout_id = GLib.timeout_add(
            TRANSITION_DURATION, self.toggle_controls_visibility
        )

    def toggle_controls_visibility(self):
        visible = self.start_children.is_visible() or self.end_children.is_visible()
        if visible != self.is_open:
            visible = not visible

        geometry = self.get_geometry()

        if geometry == X11WindowGeometry.TOP_LEFT:
            self.left_edge.set_visible(False)
            self.start_children.set_visible(False)
            self.right_edge.set_visible(visible)
            self.end_children.set_visible(visible)
        elif geometry == X11WindowGeometry.TOP_RIGHT:
            self.left_edge.set_visible(visible)
            self.start_children.set_visible(visible)
            self.right_edge.set_visible(False)
            self.end_children.set_visible(False)
        else:
            for child in self.get_children()[0].get_child().get_children():
                child.set_visible(visible)

    def bake_bar_buttons(self, widget):
        widget.add_style_class("top-bar-control-btn")
        return add_hover_cursor(widget=widget)

    def update_controls(self, source, child_controls):
        logger.debug("Updating controls", child_controls)

        if child_controls is None:
            child_controls = []

        old_left = self.left_child
        old_right = self.right_child

        # unparent controls from old containers
        self._safe_unparent_controls(old_left, old_right)

        next_left, next_right = self._create_control_containers(child_controls)

        self.left.add(next_left)
        self.right.add(next_right)

        # queue old containers for cleanup
        self._queue_cleanup([old_left, old_right])

        # update references
        self.left_child = next_left
        self.right_child = next_right
        self.right_edge.show_all()

        if self.is_open:
            self.left.set_visible_child(next_left)
            self.right.set_visible_child(next_right)

    def _safe_unparent_controls(self, *containers):
        for container in containers:
            if container in self._protected_boxes:
                continue

            try:
                for child in list(container.get_children()):
                    container.remove(child)
            except Exception as e:
                logger.error(f"Error unparenting controls: {e}")

    def _create_control_containers(self, controls: list[Gtk.Widget]) -> tuple:
        timestamp = GLib.get_monotonic_time()

        left = Box(
            name=f"left_ctrl_{timestamp}",
            style_classes=["top-bar-controls-box"],
            spacing=CONTROLS_SPACING,
        )
        right = Box(
            name=f"right_ctrl_{timestamp}",
            style_classes=["top-bar-controls-box"],
            spacing=CONTROLS_SPACING,
        )

        if not controls:
            ...
        else:
            for index, control in enumerate(controls):
                try:
                    if self._pill_ref._pos["x"] == "left":
                        target = right
                    elif self._pill_ref._pos["x"] == "right":
                        target = left
                    else:
                        target = left if index % 2 == 0 else right
                    target.add(self.bake_bar_buttons(control))
                except Exception as e:
                    logger.error(f"Error adding control {index}: {e}")

        return left, right

    def _queue_cleanup(self, boxes: list[Box]):
        for box in boxes:
            if box not in self._protected_boxes:
                self._boxes_to_clean.append(box)

        # schedule cleanup if not already scheduled
        if self._cleanup_timeout_id is None:
            self._cleanup_timeout_id = GLib.timeout_add(
                CLEANUP_DELAY, self._cleanup_scheduled_boxes
            )

    def _cleanup_scheduled_boxes(self) -> bool:
        self._cleanup_timeout_id = None

        for box in self._boxes_to_clean:
            try:
                # remove from parent stack
                if box.get_parent() == self.left:
                    self.left.remove(box)
                elif box.get_parent() == self.right:
                    self.right.remove(box)

                box.destroy()
            except Exception as e:
                logger.error(f"Error cleaning up box: {e}")

        self._boxes_to_clean.clear()
        return False

    def toggle_detach(self, detach=None):
        if detach is None:
            self.detach_mode = not self.detach_mode
            detach = self.detach_mode

        if detach:
            self.detach_edge(detach=True)
            if not self.is_open:
                return
            self.detach_controls(True)
        else:
            if self.is_open:
                self.detach_controls(detach=False)
            self.detach_edge(False)

    def detach_edge(self, detach=False):
        if detach:
            toggle_class(self.left_edge, "attach", "detach")
            toggle_class(self.right_edge, "attach", "detach")
            toggle_class(self.stack, "attach", "detach")
        else:
            toggle_class(self.left_edge, "detach", "attach")
            toggle_class(self.right_edge, "detach", "attach")
            toggle_class(self.stack, "detach", "attach")

        return False

    def detach_controls(self, detach: bool = False):
        def toggle_pushdown():
            if detach:
                toggle_class(self.start_children, "pushup", "pushdown")
                toggle_class(self.end_children, "pushup", "pushdown")
            else:
                toggle_class(self.start_children, "pushdown", "pushup")
                toggle_class(self.end_children, "pushdown", "pushup")
            return False

        def toggle_detach_controls_class():
            if detach:
                toggle_class(self.start_children, "attach", "detach")
                toggle_class(self.end_children, "attach", "detach")
            else:
                toggle_class(self.start_children, "detach", "attach")
                toggle_class(self.end_children, "detach", "attach")
            return False

        if detach:
            toggle_detach_controls_class()
            toggle_pushdown()
        else:
            toggle_pushdown()
            toggle_detach_controls_class()

    def _on_destroy(self, *args):
        # cancel all pending timeouts
        if self._cleanup_timeout_id is not None:
            GLib.source_remove(self._cleanup_timeout_id)
            self._cleanup_timeout_id = None

        if self._controls_visibility_timeout_id is not None:
            GLib.source_remove(self._controls_visibility_timeout_id)
            self._controls_visibility_timeout_id = None

        if self._detach_animation_timeout_id is not None:
            GLib.source_remove(self._detach_animation_timeout_id)
            self._detach_animation_timeout_id = None

        if self._detach_toggle_timeout_id is not None:
            GLib.source_remove(self._detach_toggle_timeout_id)
            self._detach_toggle_timeout_id = None

        if self._detach_edge_timeout_id is not None:
            GLib.source_remove(self._detach_edge_timeout_id)
            self._detach_edge_timeout_id = None

        # clear all pending boxes
        self._boxes_to_clean.clear()

    def on_delete_event(self, *_):
        # don't close me :(
        return True
