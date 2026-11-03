from typing import Literal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


class EdgeClipViewport(Gtk.Viewport):
    """
    Viewport that can be allocated narrower than its child.

    The child always keeps at least its natural width and stays pinned to
    `edge` ("start" = left, "end" = right); whatever doesn't fit is clipped
    off the opposite side. Because the minimum width reported is 0, a parent
    box never has to overflow to fit it: neighbours that grow (e.g. the
    dock's pill notch) slide over the far end of the child instead.
    """

    def __init__(
        self,
        child: Gtk.Widget,
        edge: Literal["start", "end"] = "start",
        h_expand: bool = False,
        v_expand: bool = False,
    ):
        super().__init__(hscroll_policy=Gtk.ScrollablePolicy.NATURAL)
        self.set_shadow_type(Gtk.ShadowType.NONE)
        self.set_hexpand(h_expand)
        self.set_vexpand(v_expand)
        self._edge = edge

        # the viewport reconfigures its adjustment (upper/page size) on every
        # allocation; re-pin the scroll offset to the chosen edge each time
        self.get_hadjustment().connect("changed", self._pin_to_edge)
        self.add(child)

    def _pin_to_edge(self, adj: Gtk.Adjustment):
        target = (
            adj.get_upper() - adj.get_page_size()
            if self._edge == "end"
            else adj.get_lower()
        )
        if adj.get_value() != target:
            adj.set_value(target)

    def do_get_preferred_width(self):
        _, nat = Gtk.Viewport.do_get_preferred_width(self)
        return 0, nat
