import os
import pwd

from loguru import logger
from Xlib import X
from Xlib.display import Display

from fabric import Application
from fabric.widgets.box import Box
from fabric.utils.helpers import get_relative_path, monitor_file

from .authenticator import Authenticator
from .entry import PasswordEntry
from .ui import LockContent
from .xkb import KeyTranslator, enable_xkb
from .supervisor import (
    APP_NAME,
    EXIT_UNLOCKED,
    EXIT_LOCK_FAILED,
    EXIT_ALREADY_RUNNING,
    signal_locked,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk  # type: ignore

# TODO:
# - dpms handle

GRAB_TIMEOUT_MS = 3000
GRAB_RETRY_MS = 5


class DisplayWatch:
    """Dispatch a python-xlib connection's events from the GLib main loop."""

    def __init__(self, display: Display, on_event, on_lost):
        self.display = display
        self.on_event = on_event
        self.on_lost = on_lost
        self._source = GLib.io_add_watch(
            display.fileno(),
            GLib.PRIORITY_HIGH,
            GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
            self._on_io,
        )

    def _on_io(self, _fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            logger.critical("Lost connection to the X server")
            self._source = None
            self.on_lost()
            return False
        return self.drain()

    def drain(self) -> bool:
        try:
            while self.display.pending_events():
                self.on_event(self.display.next_event())
        except Exception as e:
            logger.error(f"X event handling failed: {e}")
        return True

    def stop(self):
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None


class X11Guard:
    """Input grabs, key translation and keep-on-top, on one X connection."""

    def __init__(self, xid: int, on_key, on_lost):
        self.on_key = on_key
        self.xid = xid

        self.display = Display()
        enable_xkb(self.display)  # group/level info in key event state
        self.root = self.display.screen().root
        self.win = self.display.create_resource_object("window", xid)
        self.translator = KeyTranslator()
        self.cursor = self._blank_cursor()

        self.keyboard_grabbed = False
        self.pointer_grabbed = False

        # raise whenever any top-level window maps/moves/restacks, and when we
        # become obscured. Event masks are per connection, so they have to be
        # selected on the connection that reads the events.
        # we lowkey aggressive ;)
        self.root.change_attributes(event_mask=X.SubstructureNotifyMask)
        self.win.change_attributes(event_mask=X.VisibilityChangeMask)

        self.watch = DisplayWatch(self.display, self._on_event, on_lost)
        self.raise_window()

    def _blank_cursor(self):
        pixmap = self.root.create_pixmap(1, 1, 1)
        gc = pixmap.create_gc(foreground=0, background=0)
        pixmap.fill_rectangle(gc, 0, 0, 1, 1)
        cursor = pixmap.create_cursor(pixmap, (0, 0, 0), (0, 0, 0), 0, 0)
        gc.free()
        pixmap.free()
        return cursor

    # grabs

    def steal_focus(self):
        # may close context menus that hold grabs
        self.win.set_input_focus(X.RevertToParent, X.CurrentTime)
        self.display.flush()

    def try_grab(self) -> bool:
        if not self.pointer_grabbed:
            result = self.root.grab_pointer(
                False,
                X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask,
                X.GrabModeAsync,
                X.GrabModeAsync,
                X.NONE,
                self.cursor,
                X.CurrentTime,
            )
            self.pointer_grabbed = result == X.GrabSuccess

        if not self.keyboard_grabbed:
            result = self.root.grab_keyboard(
                False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime
            )
            self.keyboard_grabbed = result == X.GrabSuccess

        # grab replies may have buffered events
        GLib.idle_add(lambda: self.watch.drain() and False)
        return self.keyboard_grabbed and self.pointer_grabbed

    def release(self):
        self.watch.stop()
        try:
            self.display.ungrab_keyboard(X.CurrentTime)
            self.display.ungrab_pointer(X.CurrentTime)
            self.display.flush()
            self.display.close()
        except Exception as e:
            logger.warning(f"Failed to release grabs cleanly: {e}")
        self.keyboard_grabbed = self.pointer_grabbed = False

    # stacking

    def raise_window(self):
        self.win.configure(stack_mode=X.Above)
        self.display.flush()

    def _on_event(self, event):
        etype = event.type
        if etype == X.KeyPress:
            self._on_keypress(event)
        elif etype in (X.MapNotify, X.ConfigureNotify, X.CirculateNotify):
            # ignore our own restacks, we don't wanna loop forever
            if event.window.id != self.xid:
                self.raise_window()
        elif etype == X.UnmapNotify:
            # any client can unmap an override-redirect window; the root grab
            # keeps input locked, but the desktop would be visible
            if event.window.id == self.xid:
                logger.warning("Lock window was unmapped externally; remapping")
                self.win.map()
                self.raise_window()
        elif etype == X.VisibilityNotify and event.state != X.VisibilityUnobscured:
            self.raise_window()

    # keys

    def _on_keypress(self, event):
        keysym = self.translator.keysym(event.detail, event.state)
        self.on_key(
            keysym, self.translator.text(keysym), bool(event.state & X.ControlMask)
        )


class LockScreen(Gtk.Window):
    def __init__(self):
        # POPUP = override-redirect: the WM never manages or moves it, and it
        # maps even while another window is fullscreen. Default (non-RGBA)
        # visual so a compositor can never show the desktop through it.
        super().__init__(type=Gtk.WindowType.POPUP, title="Lock Screen")
        self.set_decorated(False)
        self.set_resizable(False)

        self.exit_code = EXIT_UNLOCKED
        self.guard: X11Guard | None = None
        self.authenticator = Authenticator(pwd.getpwuid(os.getuid()).pw_name)

        self.pad_left = Box()
        self.pad_right = Box()
        self.pad_top = Box(orientation="v")
        self.pad_bottom = Box(orientation="v")
        for pad in (self.pad_left, self.pad_right, self.pad_top, self.pad_bottom):
            # visibility is managed by _update_monitor_geometry, not show_all()
            pad.set_no_show_all(True)

        self._build_ui()
        self._update_monitor_geometry()

        self.connect("map-event", self._on_mapped)
        self.connect("destroy", lambda *_: self._finish(self.exit_code))

        screen = self.get_screen()
        screen.connect("monitors-changed", self._update_monitor_geometry)
        screen.connect("size-changed", self._update_monitor_geometry)

        self.realize()
        self._set_bypass_compositor()
        self.show_all()

    # ui

    def _build_ui(self):
        self.center_box = LockContent()
        self.entry = PasswordEntry(
            self.center_box,
            self.authenticator,
            on_success=lambda: self._finish(EXIT_UNLOCKED),
        )

        middle_row = Box(children=[self.pad_left, self.center_box, self.pad_right])
        # opaque everywhere, including the pads over non-primary monitors
        main = Box(
            orientation="v",
            style="background-color: var(--background);",
            children=[self.pad_top, middle_row, self.pad_bottom],
        )
        self.add(main)

    def _set_bypass_compositor(self):
        display = Display()
        try:
            xwin = display.create_resource_object("window", self.get_window().get_xid())
            xwin.change_property(
                display.intern_atom("_NET_WM_BYPASS_COMPOSITOR"),
                display.intern_atom("CARDINAL"),
                32,
                [1],
                X.PropModeReplace,
            )
            display.flush()
        finally:
            display.close()

    # geometry

    def _get_primary_geometry(self, root_width: int, root_height: int):
        """(x, y, w, h) of the primary monitor. GDK falls back to monitor 0
        itself; with zero monitors (mid hotplug/undock) cover the root."""
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return 0, 0, root_width, root_height
        geom = monitor.get_geometry()
        return geom.x, geom.y, geom.width, geom.height

    def _get_root_size(self) -> tuple[int, int]:
        display = Display()
        try:
            geom = display.screen().root.get_geometry()
            return geom.width, geom.height
        finally:
            display.close()

    def _update_monitor_geometry(self, *_):
        root_width, root_height = self._get_root_size()
        mon_x, mon_y, mon_w, mon_h = self._get_primary_geometry(root_width, root_height)

        pads = (
            (self.pad_left, mon_x, -1),
            (self.pad_right, root_width - (mon_x + mon_w), -1),
            (self.pad_top, -1, mon_y),
            (self.pad_bottom, -1, root_height - (mon_y + mon_h)),
        )
        for pad, width, height in pads:
            pad.set_size_request(width, height)
            pad.set_visible(max(width, height) > 0)

        self.center_box.set_size_request(mon_w, mon_h)
        self.set_size_request(root_width, root_height)
        self.resize(root_width, root_height)
        self.move(0, 0)
        if self.guard:
            self.guard.raise_window()

    # lifecycle

    def _on_mapped(self, *_):
        if self.guard is not None:
            return
        self.guard = X11Guard(
            self.get_window().get_xid(),
            on_key=self.entry.handle_key,
            on_lost=lambda: self._finish(1),
        )
        self.guard.steal_focus()

        attempts = GRAB_TIMEOUT_MS // GRAB_RETRY_MS

        def retry():
            nonlocal attempts
            if self.guard is None:
                return False
            if self.guard.try_grab():
                logger.info("Keyboard and pointer grabbed")
                signal_locked()
                return False
            attempts -= 1
            if attempts <= 0:
                logger.error(
                    f"Could not grab input after {GRAB_TIMEOUT_MS}ms "
                    f"(keyboard={self.guard.keyboard_grabbed}, "
                    f"pointer={self.guard.pointer_grabbed})"
                )
                self._finish(EXIT_LOCK_FAILED)
                return False
            return True

        if retry():
            GLib.timeout_add(GRAB_RETRY_MS, retry)

    def _finish(self, code: int):
        self.exit_code = code
        self.entry.password.clear()
        if self.guard is not None:
            self.guard.release()
            self.guard = None
        app = self.get_application()
        if app:
            app.quit()


def run() -> int:
    try:
        # open_client=False: Fabric's DBus client exposes Execute/Evaluate (arbitrary
        # Python), which would let any process on the session bus unlock us
        app = Application(APP_NAME, open_client=False)
    except ValueError:
        logger.warning("Lock screen already running")
        return EXIT_ALREADY_RUNNING

    lock_win = LockScreen()
    app.add_window(lock_win)

    def set_css(*_):
        app.set_stylesheet_from_file(get_relative_path("./style.css"))

    app.style_monitor = monitor_file(get_relative_path("../styles/colors.css"))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()
    return lock_win.exit_code


if __name__ == "__main__":
    raise SystemExit(run())
