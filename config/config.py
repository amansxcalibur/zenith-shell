import os
import copy
import json
import threading
from pathlib import Path
from loguru import logger

from fabric.core.service import Service, Signal
from .bindings import (
    KeyBinding,
    hydrate_binding_config,
    build_resolved_binding_instances,
)
from .info import TEMP_DIR, CACHE_DIR, CONFIG_DIR, CONFIG_FILE

from gi.repository import GLib  # type: ignore


DEFAULTS = {
    "i3": {
        "gaps": {"enabled": True, "props": {"outer": 3, "inner": 0}},
        "borders": {
            "enabled": True,
            "props": {"border_width": 2, "corner_radius": 16, "smart_borders": True},
            "matugen": True,
        },
    },
    "system": {
        "SILENT": False,
        "VERTICAL": False,
        "LOCKSCREEN": "i3lock",
        "WEATHER_LOCATION": "auto",
        "BRIGHTNESS_DEV": "auto",
        "ALLOWED_PLAYERS": ["vlc", "cmus", "firefox", "spotify", "chromium"],
    },
    "paths": {"WALLPAPERS_DIR": "~/Pictures/Wallpapers/"},
    "dashboard": {
        "WIDGETS_ENABLED": ["clock", "weather"],
        "REFRESH_INTERVAL": 5000,
        "SHOW_NOTIFICATIONS": True,
    },
    "screen_corners": {"enabled": False, "props": {"radius": 20}},
    "bar": {
        "POSITION": "bottom",
        "HEIGHT": 32,
        "SPACING": 8,
        "modules": {
            "left": [
                "actions",
                "workspaces",
                "vol_brightness_box",
                "weather_mini",
            ],
            "right": ["date_time", "battery", "systray", "power_profiles", "metrics"],
        },
    },
    "pill": {"POSITION": {"x": "center", "y": "bottom"}},
    "network": {"wifi": {"enabled": True}},
    "bluetooth": {"enabled": False},
    "top_bar": {"POSITION": "top", "HEIGHT": 32, "SPACING": 8},
    "top_pill": {"POSITION": {"x": "center", "y": "top"}},
    "bindings": {"i3": {}, "modules": {}},
}

# Keys under `paths` that are directories to be auto-created by _ensure_directories.
# Anything not listed here (e.g. a future `paths.SOME_FILE`) is left alone.
_DIRECTORY_PATH_KEYS = {}

_SAVE_DEBOUNCE_SECONDS = 0.5  # (seconds)


# TODO: Config shouldn't really create the 'paths'. It should point to the expected path.
#       Something like that should be done during install. Perhaps a better architecture...


class ConfigNode:
    """A scoped proxy for reading/writing a specific branch of the config tree."""

    def __init__(self, key_path: list[str], root: "ConfigManager"):
        self._key_path = key_path  # Absolute path from root, e.g., ['bar', 'modules']
        self._root = root
        self._listeners: list = []

    def connect(self, callback):
        """
        Register `callback(relative_path: list[str], new_value) -> None` to be
        called whenever a value at or under this node's path changes. Fires
        only for changes within this branch, not the whole tree. Returns the
        callback so it can be passed to disconnect().
        """
        self._listeners.append(callback)
        return callback

    def disconnect(self, callback):
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _dispatch(self, relative_path: list[str], value):
        for cb in list(self._listeners):
            try:
                cb(relative_path, value)
            except Exception as e:
                logger.error(f"Error in config node listener for {self._key_path}: {e}")

    def _resolve_path(self, path) -> list[str]:
        # supports "system.i3.gaps" and ["system", "i3", "gaps"].
        if isinstance(path, str):
            return path.split(".")
        return list(path)

    def get(self, path, default=None):
        keys = self._resolve_path(path)
        current = self._root.get(self._key_path + keys, default)

        # auto-expand paths
        if self._key_path and self._key_path[0] == "paths" and isinstance(current, str):
            return os.path.expanduser(current)

        return current

    def set(self, path, value):
        keys = self._resolve_path(path)

        # Delegate the actual setting to the root
        absolute_path = self._key_path + keys
        self._root.set(absolute_path, value)

    def get_node(self, path) -> "ConfigNode":
        keys = self._resolve_path(path)
        return self._root.get_node(self._key_path + keys)

    def get_all(self):
        live_data = self._root.get(self._key_path)
        return copy.deepcopy(live_data)


class ConfigManager(Service):
    @Signal
    def changed(self, key_path: object, new_value: object) -> None: ...

    def __init__(self):
        super().__init__()
        self._data = {}
        self._node_cache = {}
        self.resolved_bindings = {}

        # debounced-save machinery
        self._save_lock = threading.RLock()
        self._save_timer: threading.Timer | None = None
        self._dirty = False

        # reentrancy guard: prevents a `changed` handler from triggering
        # a nested set() -> save() -> changed() loop on the same thread.
        self._in_set = False

        self._load()
        self._ensure_directories()

    def _resolve_path(self, path: str | list[str]) -> list[str]:
        # supports "system.i3.gaps" and ["system", "i3", "gaps"].
        if isinstance(path, str):
            return path.split(".")
        return list(path)

    def _load(self):
        """Load config from file, merge with defaults"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                    self._data, needs_save = self._deep_merge(
                        DEFAULTS, copy.deepcopy(loaded_data)
                    )

                    hydrate_binding_config(self._data.get("bindings", {}))
                    self.resolved_bindings = build_resolved_binding_instances(
                        self._data.get("bindings", {})
                    )

                    if needs_save or self._data != loaded_data:
                        self._save_now()
            except Exception as e:
                logger.error(f"Error loading config.json: {e}")
                self._data = copy.deepcopy(DEFAULTS)
        else:
            self._data = copy.deepcopy(DEFAULTS)
            self._save_now()

        # fresh load invalidates any cached nodes from a previous state.
        self._node_cache.clear()

    @staticmethod
    def _deep_merge(defaults, user_data):
        """Recursively merges user data into defaults, tracking if missing keys were added."""
        merged = copy.deepcopy(defaults)
        needs_save = False

        for key, value in user_data.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key], sub_needs_save = ConfigManager._deep_merge(
                    merged[key], value
                )
                needs_save = needs_save or sub_needs_save
            else:
                if key not in merged or merged[key] != value:
                    merged[key] = copy.deepcopy(value)

        missing_keys = set(defaults.keys()) - set(user_data.keys())
        if missing_keys:
            needs_save = True

        return merged, needs_save

    def _save_now(self):
        with self._save_lock:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self._data, f, indent=4)
                self._dirty = False
            except Exception as e:
                logger.error(f"Error saving config.json: {e}")

    def _schedule_save(self):
        with self._save_lock:
            self._dirty = True
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(
                _SAVE_DEBOUNCE_SECONDS, self._flush_if_dirty
            )
            self._save_timer.daemon = True
            self._save_timer.start()

    def _flush_if_dirty(self):
        with self._save_lock:
            if self._dirty:
                self._save_now()

    def flush(self):
        """Force any pending debounced write to happen immediately. Call on shutdown."""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            if self._dirty:
                self._save_now()

    def _ensure_directories(self):
        # System/Cache Directories
        for directory in [TEMP_DIR, CACHE_DIR, CONFIG_DIR]:
            path = Path(directory).expanduser()
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created system directory: {path}")

        # Config Directories - only for keys explicitly known to hold a
        # directory path, so a future paths.SOME_FILE isn't mkdir'd by mistake.
        user_paths = self._data.get("paths", {})
        for key, folder_path in user_paths.items():
            if key not in _DIRECTORY_PATH_KEYS:
                continue
            if not isinstance(folder_path, str):
                continue
            path = Path(folder_path).expanduser()
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created configured directory: {path}")
                except Exception as e:
                    logger.warning(f"Could not create {path}: {e}")

    def get(self, path: str | list[str], default=None):
        """Get an absolute config value."""
        keys = self._resolve_path(path)
        current = self._data

        try:
            for key in keys:
                current = current[key]
        except (KeyError, TypeError):
            return default

        return current

    def _default_at(self, keys: list[str]):
        """Look up the corresponding value in DEFAULTS, if any, for type-checking."""
        current = DEFAULTS
        try:
            for key in keys:
                current = current[key]
        except (KeyError, TypeError):
            return None
        return current

    def set(self, path: str | list[str], value):
        """Set an absolute config value and notify listeners."""
        keys = self._resolve_path(path)
        if not keys:
            return

        if self._in_set:
            # A `changed` handler tried to call set() re-entrantly on the same
            # thread. Log and proceed rather than deadlocking or corrupting
            # state, but this almost always indicates a bug in the caller.
            logger.warning(
                f"Reentrant config.set() detected for path {keys}; "
                "a `changed` handler is calling set() again on the same thread."
            )

        default_value = self._default_at(keys)
        if default_value is not None and value is not None:  # noqa: SIM102
            if type(value) is not type(default_value) and not (
                isinstance(value, (int, float))
                and isinstance(default_value, (int, float))
            ):
                logger.warning(
                    f"config.set({'.'.join(keys)!r}, ...) type mismatch: "
                    f"expected {type(default_value).__name__}, got {type(value).__name__}"
                )

        current = self._data
        # second-to-last key
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

        self._schedule_save()

        self._in_set = True
        try:
            self.changed(keys, value)
            self._dispatch_to_nodes(keys, value)
        finally:
            self._in_set = False

    def _dispatch_to_nodes(self, keys: list[str], value):
        """Notify any cached ConfigNode whose scope contains the changed path."""
        for node_path, node in list(self._node_cache.items()):
            depth = len(node_path)
            if tuple(keys[:depth]) == node_path:
                GLib.idle_add(node._dispatch, keys[depth:], value)

    def get_node(self, path: str | list[str]) -> ConfigNode:
        """
        Returns a scoped ConfigNode for the given path. This is a pure read —
        it never writes to disk or mutates self._data. If the path doesn't
        exist yet, the returned node simply proxies gets/sets to where that
        data would live; the first real .set() on it (or on a descendant)
        is what actually materializes and persists it.
        """
        keys = self._resolve_path(path)

        cache_key = tuple(keys)
        if cache_key in self._node_cache:
            return self._node_cache[cache_key]

        target_data = self.get(keys)
        if target_data is not None and not isinstance(target_data, dict):
            raise TypeError(
                f"Cannot create ConfigNode: path {keys} is not a dictionary."
            )

        node = ConfigNode(keys, self)
        self._node_cache[cache_key] = node
        return node

    def reload(self):
        self._load()

    def get_all(self):
        return copy.deepcopy(self._data)

    def get_binding(self, scope: str, action: str) -> KeyBinding | None:
        return self.resolved_bindings.get(scope, {}).get(action)

    def get_all_scoped_bindings(self, scope: str) -> list[KeyBinding]:
        return list(self.resolved_bindings.get(scope, {}).values())

    # --- Convenience Properties ---

    @property
    def SILENT(self):
        return self.get("system.SILENT")

    @SILENT.setter
    def SILENT(self, value):
        self.set("system.SILENT", value)

    @property
    def VERTICAL(self):
        return self.get("system.VERTICAL")

    @VERTICAL.setter
    def VERTICAL(self, value):
        self.set("system.VERTICAL", value)

    @property
    def BRIGHTNESS_DEV(self):
        return self.get("system.BRIGHTNESS_DEV")

    @BRIGHTNESS_DEV.setter
    def BRIGHTNESS_DEV(self, value):
        self.set("system.BRIGHTNESS_DEV", value)

    @property
    def BAR_HEIGHT(self):
        return self.get("bar.HEIGHT")

    @BAR_HEIGHT.setter
    def BAR_HEIGHT(self, value):
        self.set("bar.HEIGHT", value)

    @property
    def WALLPAPERS_DIR(self) -> str:
        return os.path.expanduser(self.get("paths.WALLPAPERS_DIR"))

    @WALLPAPERS_DIR.setter
    def WALLPAPERS_DIR(self, value):
        self.set("paths.WALLPAPERS_DIR", value)

    @property
    def ALLOWED_PLAYERS(self):
        return self.get("system.ALLOWED_PLAYERS")

    @ALLOWED_PLAYERS.setter
    def ALLOWED_PLAYERS(self, value):
        self.set("system.ALLOWED_PLAYERS", value)


config = ConfigManager()
