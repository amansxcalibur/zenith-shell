from __future__ import annotations

from typing import TYPE_CHECKING

from fabric.widgets.eventbox import EventBox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore

if TYPE_CHECKING:
    from .hole_controller import HoleController


class HoverOverlay(EventBox):
    def __init__(self, module: Gtk.Widget, controller: HoleController):
        super().__init__(
            name="hover-overlay",
            events=["enter-notify", "leave-notify"],
            visible_window=False,
        )
        self._module = module
        self._controller = controller

        self.add(module)
        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

    def on_hover(self, widget, event):
        self._controller.hover(self)

    def on_unhover(self, widget, event):
        # hovering to an inner child widget, don't unhover
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.set_raised(False)

    def set_raised(self, raised: bool) -> None:
        if raised:
            self._module.add_style_class("raised")
        else:
            self._module.remove_style_class("raised")
