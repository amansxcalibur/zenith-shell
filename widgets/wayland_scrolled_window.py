from fabric.widgets.scrolledwindow import ScrolledWindow

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


class AutoSizingScrolledWindow(ScrolledWindow):
    """min_content_size follows the child, since (-1, -1) acts weird on wlroots"""

    def _clamped_child_size(self):
        child = self.get_child()
        if not child:
            return None
        _, natural = child.get_preferred_size()
        max_w, max_h = self.max_content_size
        eff_w = max_w if max_w > 0 else float("inf")
        eff_h = max_h if max_h > 0 else float("inf")
        return min(natural.width, eff_w), min(natural.height, eff_h)

    def do_get_preferred_width(self):
        sizes = self._clamped_child_size()
        if sizes:
            target_w, _ = sizes
            _, cur_h = self.min_content_size
            if self.min_content_size[0] != target_w:
                self.min_content_size = (target_w, cur_h)
        return Gtk.ScrolledWindow.do_get_preferred_width(self)

    def do_get_preferred_height(self):
        sizes = self._clamped_child_size()
        if sizes:
            _, target_h = sizes
            cur_w, _ = self.min_content_size
            if self.min_content_size[1] != target_h:
                self.min_content_size = (cur_w, target_h)
        return Gtk.ScrolledWindow.do_get_preferred_height(self)
