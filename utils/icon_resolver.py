# thankyou gummy (@muhchaudhary); completely rewritten

import os
import re
from collections.abc import Callable

from loguru import logger

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio  # type: ignore


MIN_SEARCH_LENGTH = 3

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix  # type: ignore

    _DesktopAppInfo = GioUnix.DesktopAppInfo
except (ValueError, ImportError):
    _DesktopAppInfo = Gio.DesktopAppInfo


def _dai(method: str, app: Gio.AppInfo, *args):
    return getattr(_DesktopAppInfo, method)(app, *args)


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def _identity_words(app: Gio.AppInfo) -> set[str]:
    """Words that name the app itself, as opposed to keywords or categories."""
    executable = os.path.basename(app.get_executable() or "")
    return (
        _words(app.get_name())
        | _words(_dai("get_generic_name", app))
        | _words(app.get_id())
        | _words(executable)
    )


class IconResolver:
    """Resolve an app id / name / WM class to an icon via its .desktop entry.

    Lookups go through GIO, so every XDG data dir (including the user's) is
    searched. Results are memoised in memory only and dropped whenever the
    installed applications change; misses are never cached.
    """

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._wm_class_index: dict[str, Gio.AppInfo] | None = None
        self._change_callbacks: list[Callable[[], None]] = []

        # keep a reference: the monitor stops emitting once it is collected
        self._monitor = Gio.AppInfoMonitor.get()
        self._monitor.connect("changed", self._on_apps_changed)

    def add_change_callback(self, callback: Callable[[], None]) -> None:
        self._change_callbacks.append(callback)

    def get_icon(self, app_id: str | None) -> str | None:
        app_id = (app_id or "").strip()
        if not app_id:
            return None

        if app_id in self._cache:
            return self._cache[app_id]

        app = self._find_app(app_id)
        icon = self._icon_string(app) if app else None
        if icon:
            logger.debug(f"[ICONS] '{app_id}' -> {app.get_id()} ({icon})")
            self._cache[app_id] = icon
        return icon

    def _find_app(self, app_id: str) -> Gio.AppInfo | None:
        # exact desktop id: "firefox", "org.gnome.Nautilus"
        for candidate in dict.fromkeys((app_id, app_id.lower())):
            app = self._from_desktop_id(f"{candidate}.desktop")
            if app:
                return app

        # StartupWMClass, the field meant for matching windows to apps
        app = self._by_wm_class().get(app_id.lower())
        if app:
            return app

        # GIO's ranked search over name, generic name, keywords and exec
        return self._search(app_id)

    @staticmethod
    def _from_desktop_id(desktop_id: str) -> Gio.AppInfo | None:
        try:
            app = _DesktopAppInfo.new(desktop_id)
        except TypeError:
            return None
        if app is None or _dai("get_is_hidden", app):
            return None
        return app

    def _by_wm_class(self) -> dict[str, Gio.AppInfo]:
        if self._wm_class_index is None:
            index = {}
            for app in _DesktopAppInfo.get_all():
                if _dai("get_is_hidden", app):
                    continue
                wm_class = _dai("get_startup_wm_class", app)
                if wm_class:
                    index.setdefault(wm_class.lower(), app)
            self._wm_class_index = index
        return self._wm_class_index

    def _search(self, app_id: str) -> Gio.AppInfo | None:
        query = _words(app_id)
        if not query or len(app_id) < MIN_SEARCH_LENGTH:
            return None

        # results come in tiers of equal score, best first; only trust the top tier
        tiers = _DesktopAppInfo.search(app_id)
        if not tiers:
            return None

        apps = [app for app in map(self._from_desktop_id, tiers[0]) if app]
        # GIO also matches keywords and substrings ("volume" -> Disks), so only
        # keep apps whose own name/id/exec contains every word of the query
        apps = [app for app in apps if query <= _identity_words(app)]
        apps = [app for app in apps if app.should_show()] or apps
        if not apps:
            return None

        # within a tier, prefer an app whose name is exactly what was asked for
        wanted = app_id.casefold()
        for app in apps:
            if (app.get_name() or "").casefold() == wanted:
                return app
        return apps[0]

    @staticmethod
    def _icon_string(app: Gio.AppInfo) -> str | None:
        icon = app.get_icon()
        if isinstance(icon, Gio.FileIcon):
            return icon.get_file().get_path()
        if isinstance(icon, Gio.ThemedIcon):
            names = icon.get_names()
            return names[0] if names else None
        return icon.to_string() if icon else None

    def _on_apps_changed(self, *_):
        self._cache.clear()
        self._wm_class_index = None
        for callback in self._change_callbacks:
            callback()
