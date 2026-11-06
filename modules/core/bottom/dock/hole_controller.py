from typing import Literal

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox

from .placement import DockPlacement
from .module_overlay import HoverOverlay
from .surface import HOLE_FLARE, DockSurface

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # type: ignore

REST_DELAY_MS = 500  # idle time before the hole returns to the outermost module


class HoleController:
    def __init__(
        self,
        surface: DockSurface,
        placement: DockPlacement,
        modules: list[Gtk.Widget],
        side: Literal["start", "end"],
    ):
        self._surface = surface
        self._side = side
        self._hovered: HoverOverlay | None = None
        self._rest_timeout: int | None = None
        # area the row is visible in, set when the row is clipped
        self._clip: Gtk.Widget | None = None

        self.hole = surface.add_hole()
        self.overlays = [HoverOverlay(module, self) for module in modules]

        # hovering past the last module collapses the hole, even though the
        # pointer never left the row
        fallback = EventBox(
            child=Box(**placement.expand_along()),
            events=["enter-notify"],
            **placement.expand_along(),
        )
        fallback.connect("enter-notify-event", lambda *_: self.collapse())

        row = Box(
            orientation=placement.orientation,
            children=(
                [*self.overlays, fallback]
                if side == "start"
                else [fallback, *self.overlays]
            ),
            **placement.expand_along(),
        )
        self.widget = EventBox(
            child=row,
            events=["leave-notify"],
            **placement.expand_along(),
        )
        self.widget.connect("leave-notify-event", self._on_leave)

        self._schedule_rest()

    def set_clip(self, clip: Gtk.Widget) -> None:
        self._clip = clip

    def hover(self, overlay: HoverOverlay) -> None:
        self._cancel_rest()
        for other in self.overlays:
            other.set_raised(other is overlay)
        self._hovered = overlay

        along = self._hole_along(overlay)
        if along is None:
            return

        start, size = along
        if not self.hole.target.is_open:
            # open in place instead of sliding in from the previous position
            self.hole.jump_to(start=start + size / 2, size=0)
        self.hole.animate_to(
            start=start,
            size=size,
            depth=self._surface.thickness,
            flare=HOLE_FLARE,
        )

    def collapse(self) -> None:
        self._hovered = None
        for overlay in self.overlays:
            overlay.set_raised(False)

        target = self.hole.target
        self.hole.animate_to(
            start=target.start + target.size / 2, size=0, depth=0, flare=0
        )
        self._schedule_rest()

    def sync_geometry(self) -> None:
        """Keep the hole on the hovered module as the layout changes."""
        if self._hovered is None:
            return

        along = self._hole_along(self._hovered)
        if along is None:
            return

        start, size = along
        depth = self._surface.thickness
        current = self.hole.current
        if self.hole.animating:
            self.hole.animate_to(start=start, size=size, depth=depth)
        elif (start, size, depth) != (current.start, current.size, current.depth):
            # a module resizing frame by frame: easing each step would lag
            self.hole.jump_to(start=start, size=size, depth=depth)

    def _hole_along(self, overlay: HoverOverlay) -> tuple[float, float] | None:
        along = self._surface.rect_along(overlay)
        if along is None:
            return None

        start, size = along
        end = start + size
        if self._clip is not None and (clip := self._surface.rect_along(self._clip)):
            start = max(start, clip[0])
            end = min(end, clip[0] + clip[1])
        return start, max(0, end - start)

    def _on_leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.collapse()

    def _schedule_rest(self) -> None:
        self._cancel_rest()
        self._rest_timeout = GLib.timeout_add(REST_DELAY_MS, self._rest)

    def _cancel_rest(self) -> None:
        if self._rest_timeout is not None:
            GLib.source_remove(self._rest_timeout)
            self._rest_timeout = None

    def _rest(self) -> bool:
        self._rest_timeout = None
        if self.overlays:
            self.hover(self.overlays[0 if self._side == "start" else -1])
        return False
