from typing import Literal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


class EdgeClipViewport(Gtk.Viewport):
    """
    Viewport that can be allocated smaller than its child along one axis.

    The child always keeps at least its natural size on that axis and stays
    pinned to `edge` ("start" = left/top, "end" = right/bottom); whatever
    doesn't fit is clipped off the opposite side. Because the minimum size
    reported is 0, a parent box never has to overflow to fit it: neighbours
    that grow (e.g. the dock's pill notch) slide over the far end of the child
    instead.
    """

    def __init__(
        self,
        child: Gtk.Widget,
        edge: Literal["start", "end"] = "start",
        orientation: Literal["h", "v"] = "h",
        h_expand: bool = False,
        v_expand: bool = False,
    ):
        self._vertical = orientation == "v"
        policy = Gtk.ScrollablePolicy.NATURAL
        if self._vertical:
            super().__init__(vscroll_policy=policy)
        else:
            super().__init__(hscroll_policy=policy)
        self.set_shadow_type(Gtk.ShadowType.NONE)
        self.set_hexpand(h_expand)
        self.set_vexpand(v_expand)
        self._edge = edge

        # the viewport reconfigures its adjustment (upper/page size) on every
        # allocation; re-pin the scroll offset to the chosen edge each time
        adjustment = (
            self.get_vadjustment() if self._vertical else self.get_hadjustment()
        )
        adjustment.connect("changed", self._pin_to_edge)
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
        minimum, natural = Gtk.Viewport.do_get_preferred_width(self)
        return (minimum, natural) if self._vertical else (0, natural)

    def do_get_preferred_height(self):
        minimum, natural = Gtk.Viewport.do_get_preferred_height(self)
        return (0, natural) if self._vertical else (minimum, natural)
