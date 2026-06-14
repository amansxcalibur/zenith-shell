from fabric.widgets.stack import Stack
from fabric.widgets.widget import Widget

from .scale_box import AnimatedScaleBox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib


class ElasticStack(AnimatedScaleBox):
    def __init__(
        self,
        bounce_duration=0.35,
        bounce_bezier=(0.34, 1.56, 0.64, 1.0),
        children=None,
        **stack_kwargs,
    ):
        self._inner_stack = Stack(**stack_kwargs)
        self._bounce_duration = bounce_duration
        self._bounce_bezier = bounce_bezier
        self._last_visible: Widget | None = None
        self._pending_overshoot: float | None = None

        super().__init__(scale=1.0, child=self._inner_stack)

        if children is not None:
            if isinstance(children, Widget):
                children = [children]
            for child in children:
                self._inner_stack.add(child)

            self._last_visible = self._inner_stack.get_visible_child()

        self._inner_stack.connect(
            "notify::visible-child", self._on_visible_child_changed
        )
        self._inner_stack.connect(
            "notify::transition-running", self._on_transition_running_changed
        )

    def get_inner_stack(self) -> Stack:
        return self._inner_stack

    def add_named(self, widget, name):
        self._inner_stack.add_named(widget, name)

    def set_visible_child(self, widget):
        self._inner_stack.set_visible_child(widget)

    def set_visible_child_name(self, name):
        self._inner_stack.set_visible_child_name(name)

    def get_visible_child(self):
        return self._inner_stack.get_visible_child()

    def get_visible_child_name(self):
        return self._inner_stack.get_visible_child_name()

    def _get_natural_area(self, widget):
        _, nat = widget.get_preferred_size()
        return nat.width * nat.height

    def _on_visible_child_changed(self, stack, _param):
        incoming = stack.get_visible_child()
        if incoming is None:
            self._last_visible = None
            return

        if self._last_visible is not None and self._last_visible is not incoming:
            overshoot = (
                1.20
                if self._get_natural_area(incoming)
                >= self._get_natural_area(self._last_visible)
                else 0.80
            )
            duration_s = stack.get_transition_duration() / 1000.0

            # animate to overshoot over the same duration as the stack transition
            self.animate_to(overshoot, duration=duration_s, bezier=(0.4, 0.0, 1.0, 1.0))

            # after transition completes, spring back to 1.0
            GLib.timeout_add(
                stack.get_transition_duration(),
                self._spring_back,
            )

        self._last_visible = incoming

    def _spring_back(self):
        self.animate_to(1.0, duration=self._bounce_duration, bezier=self._bounce_bezier)
        return False  # don't repeat

    def _on_transition_running_changed(self, stack, _param):
        if stack.get_transition_running() or self._pending_overshoot is None:
            return
        overshoot = self._pending_overshoot
        self._pending_overshoot = None
        self._scale_x = overshoot
        self._scale_y = overshoot
        self.queue_resize()
        self.animate_to(1.0, duration=self._bounce_duration, bezier=self._bounce_bezier)
