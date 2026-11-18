import ctypes
import ctypes.util
import os

from loguru import logger

import icons
from config.info import IS_WAYLAND, SHELL_NAME
from modules.tile import TileSmall
from services.rfkill import RfkillService, TYPE_ALL

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # type: ignore


class X11ScreenSaver:
    """Resets the X screensaver timer through Xlib on a private connection, the
    same call `xset s reset` makes."""

    def __init__(self):
        self._lib = None
        self._display = None
        try:
            lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        except OSError as e:
            logger.warning(f"[Caffeine] libX11 not found: {e}")
            return
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XOpenDisplay.restype = ctypes.c_void_p
        for name in ("XResetScreenSaver", "XFlush", "XCloseDisplay"):
            getattr(lib, name).argtypes = [ctypes.c_void_p]
        self._display = lib.XOpenDisplay(None)
        if not self._display:
            logger.warning("[Caffeine] couldn't open the X display")
            return
        self._lib = lib

    def reset(self):
        if self._display:
            self._lib.XResetScreenSaver(self._display)
            self._lib.XFlush(self._display)

    def close(self):
        if self._display:
            self._lib.XCloseDisplay(self._display)
            self._display = None


class CaffeineTile(TileSmall):
    """Keeps the screen from idling (dimming, locking, blanking) while on.

    - logind idle lock: swayidle, hypridle and logind's own IdleAction respect
      it. It lives as long as the fd logind hands back, so the kernel drops it
      if the shell dies.
    - X11: also resets the X screensaver timer, which xss-lock, DPMS and the X
      screensaver run on and which ignore logind.

    Sleep is left alone, so suspending on purpose still works.
    """

    X11_RESET_SECONDS = 10  # well under any realistic screensaver/DPMS timeout

    def __init__(self, **kwargs):
        super().__init__(
            markup=icons.material.coffee.symbol(), label="Caffeine", **kwargs
        )
        self._lock_fd: int | None = None
        self._x11_timer = None
        self._x11: X11ScreenSaver | None = None

    def handle_state_toggle(self, *_):
        if self.state:
            self.disable()
        else:
            self.enable()

    def enable(self):
        self._lock_fd = self._take_idle_lock()
        if not IS_WAYLAND:
            self._x11 = X11ScreenSaver()
            self._x11.reset()
            self._x11_timer = GLib.timeout_add_seconds(
                self.X11_RESET_SECONDS, self._reset_x11_idle
            )
        self.set_state(True)

    def disable(self):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self._x11_timer is not None:
            GLib.source_remove(self._x11_timer)
            self._x11_timer = None
        if self._x11 is not None:
            self._x11.close()
            self._x11 = None
        self.set_state(False)

    @staticmethod
    def _take_idle_lock() -> int | None:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            result, fds = bus.call_with_unix_fd_list_sync(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                "Inhibit",
                GLib.Variant(
                    "(ssss)", ("idle", f"{SHELL_NAME}-shell", "Caffeine", "block")
                ),
                GLib.VariantType("(h)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None,
                None,
            )
            return fds.steal_fds()[result.unpack()[0]]
        except GLib.Error as e:
            logger.warning(f"[Caffeine] couldn't take a logind idle lock: {e.message}")
            return None

    def _reset_x11_idle(self) -> bool:
        self._x11.reset()
        return True


class AirplaneModeTile(TileSmall):
    def __init__(self, **kwargs):
        super().__init__(
            markup=icons.material.airplane.symbol(), label="Airplane mode", **kwargs
        )
        self.service = RfkillService()
        self._restore: set[int] | None = None
        self.service.connect("changed", lambda *_: self.update_visual())
        self.update_visual()

    def update_visual(self):
        service = self.service
        if not service.available:
            self.set_state(False, "No radios found")
            self.set_sensitive(False)
            return
        self.set_sensitive(True)
        if service.all_blocked and service.any_hard_blocked:
            status = "On (hardware switch)"
        elif not service.writable:
            status = "No permission to change radios"
        else:
            status = None
        self.set_state(service.all_blocked, status)

    def handle_state_toggle(self, *_):
        service = self.service
        if not service.all_blocked:
            self._restore = service.unblocked_types()
            service.set_blocked(TYPE_ALL, True)
        else:
            # turned on somewhere else (or before a restart): bring all back
            types = self._restore or service.present_types()
            for radio_type in types:
                service.set_blocked(radio_type, False)
            self._restore = None
        # the visual follows the kernel's event, not what we asked for
        self.update_visual()
