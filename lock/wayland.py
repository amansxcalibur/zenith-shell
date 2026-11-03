import os
import pwd

from loguru import logger

from fabric import Application
from fabric.widgets.window import Window
from fabric.utils.helpers import get_relative_path, monitor_file

from .authenticator import Authenticator
from .entry import PasswordEntry
from .ui import LockContent
from .supervisor import (
    EXIT_UNLOCKED,
    EXIT_LOCK_FAILED,
    EXIT_ALREADY_RUNNING,
    signal_locked,
)

import gi

gi.require_version("GtkSessionLock", "0.1")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GtkSessionLock  # type: ignore

APP_NAME = "zenith-lockscreen-wayland"


class LockSurface(Window):
    def __init__(self, manager: "LockManager", monitor: Gdk.Monitor):
        super().__init__(visible=False, all_visible=False)

        geo = monitor.get_geometry()
        self.set_default_size(geo.width, geo.height)
        self.set_size_request(geo.width, geo.height)

        self.content = LockContent(h_expand=True, v_expand=True)
        self.entry = PasswordEntry(
            self.content, manager.authenticator, on_success=manager.unlock
        )
        self.children = self.content
        self.connect("key-press-event", self._on_key_press)

    def _on_key_press(self, _widget, event) -> bool:
        cp = Gdk.keyval_to_unicode(event.keyval)
        char = chr(cp) if cp and chr(cp).isprintable() else ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        self.entry.handle_key(event.keyval, char, ctrl)
        return True  # nothing else should see lock-screen input


class LockManager:
    def __init__(self, app: Application):
        self.app = app
        self.exit_code = EXIT_UNLOCKED
        self.authenticator = Authenticator(pwd.getpwuid(os.getuid()).pw_name)
        self.surfaces: dict[Gdk.Monitor, LockSurface] = {}
        self._locked = False

        self.lock = GtkSessionLock.prepare_lock()
        self.lock.connect("locked", self._on_locked)
        self.lock.connect("finished", self._on_finished)

        display = Gdk.Display.get_default()
        display.connect("monitor-added", lambda _d, mon: self._add_surface(mon))
        display.connect("monitor-removed", lambda _d, mon: self._remove_surface(mon))

    def start(self) -> bool:
        if not GtkSessionLock.is_supported():
            logger.critical("Compositor does not support ext-session-lock")
            return False

        self.lock.lock_lock()
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            self._add_surface(display.get_monitor(i))
        return True

    def _on_locked(self, *_):
        # the compositor only sends this once every output is covered/blanked
        self._locked = True
        logger.info("Session locked")
        signal_locked()

    def _on_finished(self, *_):
        # sent instead of `locked` when the compositor refuses (e.g. another
        # locker is active), or if it ends the lock on its own
        if self._locked:
            logger.warning("Compositor ended the session lock")
            self._quit(EXIT_UNLOCKED)
        else:
            logger.error("Compositor refused the session lock")
            self._quit(EXIT_LOCK_FAILED)

    def _add_surface(self, monitor: Gdk.Monitor):
        if monitor in self.surfaces:
            return
        surface = LockSurface(self, monitor)
        self.lock.new_surface(surface, monitor)
        self.app.add_window(surface)
        surface.show_all()
        self.surfaces[monitor] = surface
        logger.debug(f"Lock surface added for {monitor.get_model()}")

    def _destroy_surface(self, surface: LockSurface):
        # the role object has to go before the wl_surface, otherwise the
        # compositor kills us with "surface was destroyed before its role
        # object" - and while locked that leaves the session stuck
        surface.entry.password.clear()
        GtkSessionLock.unmap_lock_window(surface)
        self.app.remove_window(surface)
        surface.destroy()

    def _remove_surface(self, monitor: Gdk.Monitor):
        surface = self.surfaces.pop(monitor, None)
        if surface:
            self._destroy_surface(surface)

    def unlock(self):
        logger.info("Unlocking session")
        self.lock.unlock_and_destroy()
        self._quit(EXIT_UNLOCKED)

    def _quit(self, code: int):
        self.exit_code = code
        for surface in self.surfaces.values():
            self._destroy_surface(surface)
        self.surfaces.clear()
        Gdk.Display.get_default().flush()
        self.app.quit()


def run() -> int:
    try:
        # open_client=False: fabric's DBus client exposes Execute/Evaluate
        # (arbitrary Python), which would let any process unlock us
        app = Application(APP_NAME, open_client=False)
    except ValueError:
        logger.warning("Lock screen already running")
        return EXIT_ALREADY_RUNNING

    manager = LockManager(app)
    if not manager.start():
        return EXIT_LOCK_FAILED

    def set_css(*_):
        app.set_stylesheet_from_file(get_relative_path("./style.css"))

    app.style_monitor = monitor_file(get_relative_path("../styles/colors.css", 2))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()
    return manager.exit_code


if __name__ == "__main__":
    raise SystemExit(run())
