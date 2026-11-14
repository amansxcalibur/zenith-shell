from collections.abc import Callable

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore


class AnchorCanvas(Gtk.Fixed):
    def __init__(self, child: Gtk.Widget, width: int, height: int):
        super().__init__()
        self._size = (width, height)
        self._pos = (0, 0)
        self._placement_fn: Callable[[int, int], tuple[int, int] | None] | None = None
        self._child_rect: tuple[int, int, int, int] | None = None
        self._input_rect: tuple[int, int, int, int] | None = None
        self.put(child, 0, 0)
        self._child = child
        self.show()

    @property
    def child_rect(self) -> tuple[int, int, int, int] | None:
        """(x, y, width, height) of the child in canvas coordinates."""
        return self._child_rect

    def set_canvas_size(self, width: int, height: int):
        if (width, height) != self._size:
            self._size = (width, height)
            self.queue_resize()

    def set_placement_func(self, fn: Callable[[int, int], tuple[int, int] | None]):
        self._placement_fn = fn
        # place it now: callers can ask where it is before the next allocation
        _, nat = self._child.get_preferred_size()
        if (pos := fn(nat.width, nat.height)) is not None:
            self._pos = (int(pos[0]), int(pos[1]))
        self.queue_allocate()

    def get_child_position(self) -> tuple[int, int]:
        return self._pos

    def move_child(self, x: int, y: int):
        if (x, y) != self._pos:
            self._pos = (x, y)
            # same size: no need to measure again
            self.queue_allocate()

    def do_get_preferred_width(self):
        return self._size[0], self._size[0]

    def do_get_preferred_height(self):
        return self._size[1], self._size[1]

    def do_size_allocate(self, alloc: Gdk.Rectangle):
        self.set_allocation(alloc)
        _, nat = self._child.get_preferred_size()
        w, h = nat.width, nat.height

        if self._placement_fn is not None:
            pos = self._placement_fn(w, h)
            if pos is not None:
                self._pos = (int(pos[0]), int(pos[1]))

        x, y = self._pos
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = alloc.x + x, alloc.y + y, w, h
        # before allocating: the child's size-allocate handlers read it
        self._child_rect = (x, y, w, h)
        self._child.size_allocate(rect)
        self._update_input_shape()

    def _update_input_shape(self):
        window = self.get_toplevel()
        if not isinstance(window, Gtk.Window) or self._child_rect is None:
            return
        if self._child_rect == self._input_rect and window.get_mapped():
            return
        self._input_rect = self._child_rect
        x, y, w, h = self._child_rect
        window.input_shape_combine_region(cairo.Region(cairo.RectangleInt(x, y, w, h)))

    def reapply_input_shape(self):
        self._input_rect = None
        self._update_input_shape()
