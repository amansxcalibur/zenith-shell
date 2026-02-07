import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


class WrapBox(Gtk.Container):
    """
    A custom GTK Container that mimics CSS `display: flex; flex-wrap: wrap`.
    Items are packed LTR. When a row runs out of space, it wraps to the next line.
    Rows do NOT align columns vertically (unlike Gtk.FlowBox).
    """

    def __init__(self, spacing=6):
        super().__init__()
        self._children = []
        self._spacing = spacing
        self.set_has_window(False)  # We draw directly on the parent window

    def do_add(self, widget):
        self._children.append(widget)
        widget.set_parent(self)
        self.queue_resize()  # Trigger recalculation

    def do_remove(self, widget):
        if widget in self._children:
            self._children.remove(widget)
            widget.unparent()
            self.queue_resize()

    def do_forall(self, include_internals, callback, *args):
        for child in self._children:
            callback(child, *args)

    def do_get_request_mode(self):
        # Tells GTK "My height depends on how wide you make me"
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_get_preferred_width(self):
        # Calculate minimum width (widest single child) and natural width (all in one row)
        min_w = 0
        nat_w = 0
        for child in self._children:
            if not child.get_visible():
                continue
            c_min, c_nat = child.get_preferred_width()
            min_w = max(min_w, c_min)
            nat_w += c_nat + self._spacing

        # Remove trailing spacing
        if nat_w > 0:
            nat_w -= self._spacing
        return (min_w, nat_w)

    def do_get_preferred_height_for_width(self, width):
        # We must simulate the layout here to tell the parent window how tall we need to be.
        # This prevents the scrollbar from jumping or cutting off content.
        height = self._layout_children(width, apply_allocation=False)
        return (height, height)

    def do_size_allocate(self, allocation):
        self.set_allocation(allocation)
        self._layout_children(
            allocation.width,
            apply_allocation=True,
            start_x=allocation.x,
            start_y=allocation.y,
        )

    def _layout_children(
        self, avail_width, apply_allocation=False, start_x=0, start_y=0
    ):
        if avail_width <= 0:
            return 0

        x = y = line_height = 0
        visible = tuple(c for c in self._children if c.get_visible())
        alloc = Gdk.Rectangle()

        for child in visible:
            c_min, c_nat = child.get_preferred_width()
            child_width = min(c_nat, avail_width)
            _, c_nat_h = child.get_preferred_height_for_width(child_width)

            m_start = child.get_margin_start()
            m_end = child.get_margin_end()
            m_top = child.get_margin_top()
            m_bottom = child.get_margin_bottom()

            total_w = child_width + m_start + m_end
            total_h = c_nat_h + m_top + m_bottom

            if x + total_w > avail_width and x > 0:
                x = 0
                y += line_height + self._spacing
                line_height = 0

            if apply_allocation:
                alloc.x = start_x + x + m_start
                alloc.y = start_y + y + m_top
                alloc.width = child_width
                alloc.height = c_nat_h
                child.size_allocate(alloc)

            x += total_w + self._spacing
            line_height = max(line_height, total_h)

        return y + line_height
