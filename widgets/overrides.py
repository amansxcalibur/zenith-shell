from fabric.widgets.x11 import X11Window

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class PatchedX11Window(X11Window):
    """
    Subclass that patches the `pass-through` behavior when
    `Gtk.StyleContext` uses `* { all: unset }`.
    """

    # bypass fabric's Window.do_size_allocate implementation
    def do_size_allocate(self, alloc):
        Gtk.Window.do_size_allocate(self, alloc)  # type: ignore

    def do_map_event(self, alloc):
        Gtk.Window.do_map_event(self, alloc)  # type: ignore

        return self.set_pass_through(self._pass_through)
