import os
import copy
import json
import time
import shutil
import threading
import subprocess
from pathlib import Path
from loguru import logger

from fabric.core.service import Service, Signal
from .bindings import (
    KeyBinding,
    hydrate_binding_config,
    build_resolved_binding_instances,
)
from .info import TEMP_DIR, CACHE_DIR, USER_CONFIG_DIR, CONFIG_FILE

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
        "BRIGHTNESS_DEV": "auto",
        "IGNORED_PLAYERS": ["playerctld", "kdeconnect", "plasma-browser-integration"],
    },
    "theme": {"mode": "dark", "scheme": "fidelity"},
    "paths": {"WALLPAPERS_DIR": "~/Pictures/Wallpapers/"},
    "screen_corners": {"enabled": False, "props": {"radius": 20}},
    "bar": {
        "POSITION": "bottom",
        "PADDING": 2,
        "BORDER": False,
        "ACTION": "restart",
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
    "top_pill": {"POSITION": {"x": "center", "y": "top"}},
    "bindings": {"i3": {}, "modules": {}},
}

# Keys under `paths` that are directories to be auto-created by _ensure_directories.
# Anything not listed here (e.g. a future `paths.SOME_FILE`) is left alone.
_DIRECTORY_PATH_KEYS = {}

# Keys removed from DEFAULTS; stripped from existing config files on load.
_OBSOLETE_KEYS = [
    ("system", "ALLOWED_PLAYERS"),
    ("system", "WEATHER_LOCATION"),
    ("dashboard",),
    ("bar", "HEIGHT"),
    ("bar", "SPACING"),
    ("top_bar",),
]

_SAVE_DEBOUNCE_SECONDS = 0.5


# TODO: Config shouldn't really create the 'paths'. It should point to the expected path.
#       Something like that should be done during install. Perhaps a better architecture...


def _kind_name(default) -> str:
    """How to describe the expected type to someone editing config.json."""
    if isinstance(default, bool):
        return "true or false"
    if isinstance(default, (int, float)):
        return "a number"
    if isinstance(default, str):
        return "text"
    if isinstance(default, list):
        return "a list"
    return "an object"


def _same_kind(value, default) -> bool:
    """Whether a loaded value can stand in for its default."""
    if default is None:
        return True
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))


class ConfigNode:
    """A scoped proxy for reading/writing a specific branch of the config tree."""

    def __init__(self, key_path: list[str], root: "ConfigManager"):
        self._key_path = key_path  # Absolute path from root, e.g., ['bar', 'modules']
        self._root = root
        self._listeners: list = []

    def connect(self, callback):
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

        if self._key_path and self._key_path[0] == "paths" and isinstance(current, str):
            return os.path.expanduser(current)

        if isinstance(current, (dict, list)):
            return copy.deepcopy(current)

        return current

    def set(self, path, value):
        keys = self._resolve_path(path)

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

        self._save_lock = threading.RLock()
        self._save_timer: threading.Timer | None = None
        self._dirty = False

        # reentrancy guard: prevents a `changed` handler from triggering
        # a nested set() -> save() -> changed() loop on the same thread.
        self._in_set = False

        # set while config.json exists but couldn't be read; the file is left
        # alone until a save would replace it, which backs it up first
        self._unreadable_file = False

        self._load()
        self._ensure_directories()

    def _resolve_path(self, path: str | list[str]) -> list[str]:
        # supports "system.i3.gaps" and ["system", "i3", "gaps"].
        if isinstance(path, str):
            return path.split(".")
        return list(path)

    def _load(self):
        loaded_data = None
        self._unreadable_file = False
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                if not isinstance(loaded_data, dict):
                    raise TypeError("top level is not a JSON object")
                rejected: list[str] = []
                self._data, _ = self._deep_merge(
                    DEFAULTS, copy.deepcopy(loaded_data), rejected=rejected
                )
                self._drop_obsolete_keys()
                if rejected:
                    logger.warning(
                        "config.json: wrong type for "
                        f"{'; '.join(rejected)}; using the defaults for those"
                    )
                    # as with an unreadable file: leave it for the user to fix,
                    # and back it up if a save has to replace it
                    self._unreadable_file = True
                    self._notify(
                        "config.json has invalid values",
                        (
                            f"Using the defaults for: {'; '.join(rejected)}.\n\n"
                            "Your file is untouched; fix it and restart the shell."
                        ),
                    )
            except Exception as e:
                logger.error(f"Error loading config.json: {e}; using defaults")
                self._unreadable_file = True
                self._notify(
                    "config.json could not be read",
                    (
                        f"{e}\n\nZenith is using default settings. Your file "
                        "is untouched; fix it and restart the shell."
                    ),
                )
                loaded_data = None

        if loaded_data is None:
            self._data = copy.deepcopy(DEFAULTS)

        # every path needs resolved bindings, or the generated i3/sway
        # config ends up with no Zenith keybindings at all
        hydrate_binding_config(self._data.setdefault("bindings", {}))
        self.resolved_bindings = build_resolved_binding_instances(
            self._data["bindings"]
        )

        # write back merged defaults / a fresh file, but never over a file we
        # couldn't read: the user is likely about to fix it by hand
        if not self._unreadable_file and self._data != loaded_data:
            self._save_now()

        self._node_cache.clear()

    def _drop_obsolete_keys(self):
        for path in _OBSOLETE_KEYS:
            *parents, leaf = path
            node = self._data
            for key in parents:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, dict) and node.pop(leaf, None) is not None:
                logger.info(f"Removed obsolete config key {'.'.join(path)}")

    @staticmethod
    def _deep_merge(defaults, user_data, rejected=None, _path=()):
        """Recursively merges user data into defaults, tracking if missing keys were added.

        A value whose type doesn't match its default (`"bar": null`) keeps the
        default; its dotted path is appended to `rejected`."""
        merged = copy.deepcopy(defaults)
        needs_save = False

        for key, value in user_data.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key], sub_needs_save = ConfigManager._deep_merge(
                    merged[key], value, rejected, (*_path, key)
                )
                needs_save = needs_save or sub_needs_save
            elif key in merged and not _same_kind(value, merged[key]):
                if rejected is not None:
                    rejected.append(
                        f"{'.'.join((*_path, key))} "
                        f"(should be {_kind_name(merged[key])})"
                    )
            else:
                if key not in merged or merged[key] != value:
                    merged[key] = copy.deepcopy(value)

        missing_keys = set(defaults.keys()) - set(user_data.keys())
        if missing_keys:
            needs_save = True

        return merged, needs_save

    def _save_now(self):
        with self._save_lock:
            os.makedirs(USER_CONFIG_DIR, exist_ok=True)
            if self._unreadable_file:
                if not self._backup_unreadable_file():
                    return  # keep the user's file rather than lose it
                self._unreadable_file = False
            # write-then-rename so a crash mid-save can't leave a truncated file
            tmp_path = f"{CONFIG_FILE}.tmp"
            try:
                with open(tmp_path, "w") as f:
                    json.dump(self._data, f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, CONFIG_FILE)
                self._dirty = False
            except Exception as e:
                logger.error(f"Error saving config.json: {e}")
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _backup_unreadable_file(self) -> bool:
        if not os.path.exists(CONFIG_FILE):
            return True
        backup = f"{CONFIG_FILE}.broken-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            shutil.copy2(CONFIG_FILE, backup)
        except OSError as e:
            logger.error(f"Not saving: could not back up unreadable config.json: {e}")
            return False
        logger.warning(f"Kept the previous config.json as {backup} before saving")
        return True

    @staticmethod
    def _notify(summary: str, body: str):
        if shutil.which("notify-send"):
            subprocess.Popen(
                [
                    "notify-send",
                    "-u",
                    "critical",
                    "-a",
                    "Zenith",
                    summary,
                    # notification bodies are markup
                    GLib.markup_escape_text(body),
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

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
        for directory in [TEMP_DIR, CACHE_DIR, USER_CONFIG_DIR]:
            path = Path(directory).expanduser()
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created system directory: {path}")

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
        keys = self._resolve_path(path)
        if not keys:
            return

        if self._in_set:
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
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        if keys[-1] in current and current[keys[-1]] == value:
            return

        current[keys[-1]] = value

        self._schedule_save()

        self._in_set = True
        try:
            self.changed(keys, value)
            self._dispatch_to_nodes(keys, value)
        finally:
            self._in_set = False

    def update_bulk(self, staged_data: dict, sync: bool = True):
        def walk(updates: dict, path: list[str]):
            for key, value in updates.items():
                if isinstance(value, dict) and value:
                    walk(value, path + [key])
                else:
                    self.set(path + [key], value)

        walk(staged_data, [])

        if sync:
            self.flush()

    def _dispatch_to_nodes(self, keys: list[str], value):
        """Notify any cached ConfigNode whose scope contains the changed path."""
        for node_path, node in list(self._node_cache.items()):
            depth = len(node_path)
            if tuple(keys[:depth]) == node_path:
                GLib.idle_add(node._dispatch, keys[depth:], value)

    def get_node(self, path: str | list[str]) -> ConfigNode:
        """Pure read: a missing path is only created by the first set() on the node."""
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
    def WALLPAPERS_DIR(self) -> str:
        return os.path.expanduser(self.get("paths.WALLPAPERS_DIR"))

    @WALLPAPERS_DIR.setter
    def WALLPAPERS_DIR(self, value):
        self.set("paths.WALLPAPERS_DIR", value)

    @property
    def IGNORED_PLAYERS(self) -> list[str]:
        return self.get("system.IGNORED_PLAYERS")

    @IGNORED_PLAYERS.setter
    def IGNORED_PLAYERS(self, value):
        self.set("system.IGNORED_PLAYERS", value)


config = ConfigManager()
