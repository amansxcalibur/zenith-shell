import cairo
from loguru import logger

from fabric.widgets.x11 import X11Window
from fabric.widgets.svg import Svg as FabricSvg

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg, Gtk # type: ignore


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


class PinnedX11Window(PatchedX11Window):
    """
    X11 window that sends its position together with every resize, so an
    edge-anchored window (e.g. bottom/center/right) stays put while its
    content animates its size.

    Without this, X grows the window from its top-left corner first and the
    owner only re-positions it after the ConfigureNotify round trip, which
    shows as a frame of overshoot on every resize step.

    The owner supplies `placement_fn(width, height) -> (x, y) | None` via
    `set_placement_func`; returning None falls back to GTK's plain resize
    (e.g. while the user drags the window).
    """

    # class-level defaults: vfuncs can run during the parent constructor,
    # before any instance attribute would have been assigned
    _placement_fn = None
    # last (width, height) sent to the X server. get_size()/get_allocation()
    # lag behind a resize until the WM's ConfigureNotify arrives
    _committed_size = None
    # size sent via move_resize whose allocation hasn't arrived yet
    _pending_size = None
    _last_placed = None

    def set_placement_func(self, fn):
        self._placement_fn = fn

    def current_size(self) -> tuple[int, int]:
        if self._pending_size is not None:
            return self._pending_size
        if self._committed_size is not None:
            return self._committed_size
        return tuple(self.get_size())  # type: ignore

    def place(self, x: int, y: int):
        # move the GdkWindow directly so GTK's remembered position request
        # can't go stale relative to the move_resize calls below
        pos = (int(x), int(y))
        win = self.get_window()
        if win is None:
            self.move(*pos)
            return
        if pos != self._last_placed:
            win.move(*pos)
            self._last_placed = pos

    def do_check_resize(self):
        fn = self._placement_fn
        if fn is not None and self.get_mapped():
            try:
                _, nat = self.get_preferred_size()
                size = (nat.width, nat.height)
                win = self.get_window()
                # compare against what we last sent; the GdkWindow size lags
                # until ConfigureNotify, which would resend the same request
                if win and size != self.current_size():
                    pos = fn(*size)
                    if pos is None:
                        self._pending_size = None
                    else:
                        pos = (int(pos[0]), int(pos[1]))
                        win.move_resize(*pos, *size)
                        self._pending_size = size
                        self._last_placed = pos
            except Exception as e:
                logger.error(f"do_check_resize atomic move_resize failed: {e}")

        Gtk.Window.do_check_resize(self)  # type: ignore

    def do_size_allocate(self, alloc):
        # GTK may allocate from an older ConfigureNotify after we already sent
        # a newer move_resize; keep using the pending size until it catches up
        size = (alloc.width, alloc.height)
        if self._pending_size == size or not self.get_mapped():
            self._pending_size = None
        if self._pending_size is None:
            self._committed_size = size

        fn = self._placement_fn
        if fn is not None and self.get_mapped():
            try:
                pos = fn(*self.current_size())
                if pos is not None:
                    self.place(*pos)
            except Exception as e:
                logger.error(f"do_size_allocate placement failed: {e}")

        Gtk.Window.do_size_allocate(self, alloc)  # type: ignore


class Svg(FabricSvg):
    """
    Adds dynamic `color` support sourced from `Gtk.StyleContext`.
    """

    def do_draw(self, cr: cairo.Context):
        if not self._handle:
            return

        context = self.get_style_context()
        state = context.get_state()
        color = context.get_color(state)

        bridge_css = f"""
            * {{ 
                color: rgba({int(color.red * 255)}, {int(color.green * 255)}, {int(color.blue * 255)}, {color.alpha})
            }}
        """

        if self._style_compiled:
            final_style = bridge_css + self._style_compiled
        else:
            final_style = bridge_css

        if not self._handle.set_stylesheet(final_style.encode()):
            logger.error(
                "[Svg] Failed to apply styles, probably invalid style property"
            )

        alloc = self.get_allocation()
        width: int = alloc.width  # type: ignore
        height: int = alloc.height  # type: ignore

        rect = Rsvg.Rectangle()
        rect.x = rect.y = 0
        rect.width = width  # type: ignore
        rect.height = height  # type: ignore

        cr.save()
        self._handle.render_document(cr, rect)
        cr.restore()
