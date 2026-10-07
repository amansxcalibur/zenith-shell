from loguru import logger

from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.widgets.window import Window
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox
from fabric.utils.helpers import get_relative_path, monitor_file

from widgets.shapes import Pill, Circle, WavyCircle, Ellipse, Pentagon
from modules.weather import WeatherPill
from modules.wavy_clock import WavyClock
from modules.wallpaper import WallpaperService
from config.info import USERNAME

from .authenticator import Authenticator

import gi

gi.require_version("GtkSessionLock", "0.1")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GtkSessionLock  # type: ignore

# # DEBUG-ONLY escape hatch for testing.
# DEBUG_UNLOCK = os.environ.get("ZENITH_LOCK_DEBUG") == "1"

_FLASH_NEUTRAL_RGB = [1, 1, 1]
_FLASH_ERROR_RGB = [1, 0, 0]
_FLASH_BUSY_RGB = [0, 0, 1]


class LockSurface(Window):
    """One per-monitor lock surface. Owns its own password buffer;
    the session only unlocks when LockManager says so."""

    def __init__(self, manager: "LockManager", monitor: Gdk.Monitor):
        self.manager = manager
        self.monitor = monitor
        self.text = ""
        super().__init__(visible=False, all_visible=False)

        geo = self.monitor.get_geometry()
        self.set_default_size(geo.width, geo.height)
        self.set_size_request(geo.width, geo.height)

        self._build_ui()
        self.connect("key-press-event", self._on_key_press)

    def _build_ui(self):
        self.shapes = Stack(
            h_align="center",
            children=[
                Pill(dark=True),
                Circle(dark=True),
                WavyCircle(dark=True),
                Ellipse(dark=True),
                Pentagon(dark=True),
            ],
        )

        self.center_box = CenterBox(
            spacing=10,
            h_expand=True,
            center_children=[
                Box(
                    spacing=10,
                    v_align="center",
                    children=[
                        WavyClock(size=(400, 400)),
                        WeatherPill(size=(400, 400)),
                    ],
                ),
            ],
            end_children=Box(
                orientation="v",
                v_align="end",
                spacing=10,
                style="margin:20px;",
                children=[EventBox(child=self.shapes)],
            ),
        )

        wallpaper_path = (
            WallpaperService().get_lockscreen_image_path()
            or WallpaperService().get_wallpaper_path()
        )
        logger.debug(f"Using wallpaper: {wallpaper_path}")

        content = Box(
            style=(
                f"background-image: url('{wallpaper_path}');"
                "background-position: center;"
                "background-size: cover;"
            )
            if wallpaper_path is not None
            else "background-color: var(--outline)",
            children=[self.center_box],
            h_expand=True,
            v_expand=True,
        )

        # if DEBUG_UNLOCK:
        #     content.append(
        #         Button(
        #             label="Force Unlock (DEBUG)",
        #             style="background: red; color: white;",
        #             on_clicked=self._debug_force_unlock,
        #         )
        #     )
        #     logger.warning(
        #         "ZENITH_LOCK_DEBUG=1; force-unlock button is ACTIVE. "
        #         "Do not run this build outside testing."
        #     )

        self.children = Box(orientation="v", children=content)

    # def _debug_force_unlock(self, *_):
    #     # Bypasses PAM entirely. Only exists when DEBUG_UNLOCK is set.
    #     if not DEBUG_UNLOCK:
    #         return  # belt-and-suspenders
    #     logger.warning("DEBUG force-unlock triggered; bypassing authentication")
    #     self.manager.on_auth_result(True, None)

    def _on_key_press(self, widget, event) -> bool:
        keyval = event.keyval
        if keyval == Gdk.KEY_Return:
            self._activate()
        elif keyval == Gdk.KEY_BackSpace:
            self._handle_backspace()
        elif keyval == Gdk.KEY_Escape:
            self._handle_escape()
        else:
            ch = Gdk.keyval_to_unicode(keyval)
            if ch and chr(ch).isprintable():
                self._handle_character(chr(ch))
        return (
            True  # consume unconditionally — nothing else should see lock-screen input
        )

    def _handle_backspace(self):
        if not self.text:
            self._flash(_FLASH_NEUTRAL_RGB)
            return
        self._cycle_shape(forward=False)
        self.text = self.text[:-1]
        self._flash(_FLASH_NEUTRAL_RGB if not self.text else _FLASH_ERROR_RGB)

    def _handle_escape(self):
        self.text = ""
        self.shapes.set_visible_child(self.shapes.get_children()[0])
        self._flash(_FLASH_NEUTRAL_RGB)

    def _handle_character(self, char: str):
        self.text += char
        self._cycle_shape(forward=True)

    def _activate(self):
        if not self.text or self.manager.authenticator.is_authenticating():
            return
        self._flash(_FLASH_BUSY_RGB)
        # Only THIS surface's buffer is sent; every surface clears in lockstep
        # on the result, since any monitor's Enter key can unlock the session.
        self.manager.authenticator.authenticate(self.text, self.manager.on_auth_result)
        self.text = ""

    def _flash(self, rgb: list):
        """Briefly tint the active shape, then reset it on the next idle tick."""
        shape = self.shapes.get_visible_child()
        shape.set_color(rgb=rgb, redraw=True)
        GLib.idle_add(lambda: shape.set_color(rgb=None, redraw=False))

    def _cycle_shape(self, forward: bool = True):
        children = self.shapes.get_children()
        if not children:
            return
        current = children.index(self.shapes.get_visible_child())
        next_index = (current + (1 if forward else -1)) % len(children)
        self.shapes.set_visible_child(children[next_index])

    # called by LockManager
    def clear_for_retry(self, message: str):
        self._flash(_FLASH_ERROR_RGB)
        self.text = ""


class LockManager:
    def __init__(self):
        self.lock = GtkSessionLock.prepare_lock()
        self.authenticator = Authenticator(USERNAME)
        self.surfaces: dict[int, LockSurface] = {}

        display = Gdk.Display.get_default()
        display.connect("monitor-added", self._on_monitor_added)
        display.connect("monitor-removed", self._on_monitor_removed)

    def get_surfaces(self) -> dict[int, LockSurface]:
        return self.surfaces

    def start(self):
        if not GtkSessionLock.is_supported():
            logger.critical("GtkSessionLock refused - compositor may not support it")
            raise RuntimeError("session lock unavailable")

        self.lock.lock_lock()
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            self._add_surface(display.get_monitor(i))

    def _add_surface(self, monitor: Gdk.Monitor):
        surface = LockSurface(self, monitor)
        self.lock.new_surface(surface, monitor)
        surface.show_all()
        self.surfaces[id(monitor)] = surface
        logger.debug(f"Added lock surface for monitor {id(monitor)}")

    def _on_monitor_added(self, display, monitor):
        logger.info("Monitor added, locking it too")
        self._add_surface(monitor)

    def _on_monitor_removed(self, display, monitor):
        surface = self.surfaces.pop(id(monitor), None)
        if surface:
            surface.destroy()

    def on_auth_result(self, success: bool, message: str | None):
        if success:
            logger.info("Authentication successful - unlocking all surfaces...")
            self.lock.unlock_and_destroy()
            for s in self.surfaces.values():
                s.destroy()
            self.surfaces.clear()
        else:
            logger.warning(f"Authentication failed: {message}")
            for s in self.surfaces.values():
                s.clear_for_retry(message or "Incorrect password")


def run():
    WallpaperService().initialize()
    manager = LockManager()
    manager.start()

    app = Application("zenith-lockscreen-wayland", *manager.get_surfaces().values())

    def set_css(*_):
        app.set_stylesheet_from_file(get_relative_path("./style.css"))

    app.style_monitor = monitor_file(get_relative_path("../styles/colors.css", 2))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()


if __name__ == "__main__":
    run()
