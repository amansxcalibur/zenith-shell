import os
import json
from pathlib import Path

from fabric.core.service import Service, Signal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk

DEFAULTS = {
    "system": {
        "SILENT": False,
        "VERTICAL": False,
        "BRIGHTNESS_DEV": "intel_backlight",
        "ALLOWED_PLAYERS": ["vlc", "cmus", "firefox", "spotify", "chromium"],
    },
    "paths": {"WALLPAPERS_DIR": "~/Pictures/Wallpapers/", "SCRIPTS_DIR": "~/i3scripts"},
    "dashboard": {
        "WIDGETS_ENABLED": ["clock", "weather", "system"],
        "REFRESH_INTERVAL": 5000,
        "SHOW_NOTIFICATIONS": True,
    },
    "bar": {
        "POSITION": "bottom",
        "HEIGHT": 32,
        "SPACING": 8,
        "COMPONENTS": ["workspaces", "title", "systray", "clock"],
    },
    "pill": {"POSITION": {"x": "center", "y": "bottom"}},
    "network": {"wifi": {"ON": True}},
    "top_bar": {},
    "top_pill": {"POSITION": {"x": "center", "y": "top"}},
}


# Non-configurable constants
SHELL_NAME = "zenith"
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename

TEMP_DIR = "/tmp/zenith"
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser("~/.cache/zenith-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

screen = Gdk.Display().get_default().get_default_screen()
SCREEN_WIDTH = screen.get_width()
SCREEN_HEIGHT = screen.get_height()


# TODO: Config shouldn't really create the 'paths'. It should point to the expected path.
#       Something like that should be done during install. Perhaps a better architecture...

class _ConfigNode:
    """Represents any node in the config tree (can be a dict, list, or leaf value)"""

    def __init__(self, data, parent, key_path, root):
        self._data = data
        self._parent = parent
        self._key_path = key_path  # full path like ['system', 'SILENT']
        self._root = root  # ref to ConfigManager

        # If data is a dict, wrap children as ConfigNodes
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    object.__setattr__(
                        self, key, _ConfigNode(value, self, key_path + [key], root)
                    )

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(f"No attribute '{key}'")

        if isinstance(self._data, dict) and key in self._data:
            value = self._data[key]

            # Auto-expand paths if the key path starts with 'paths'
            if (
                self._key_path
                and self._key_path[0] == "paths"
                and isinstance(value, str)
            ):
                return os.path.expanduser(value)

            return value

        raise AttributeError(
            f"Config has no attribute '{'.'.join(self._key_path + [key])}'"
        )

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return

        if isinstance(self._data, dict):
            self._data[key] = value

            # if dict, wrap it as a ConfigNode
            if isinstance(value, dict):
                object.__setattr__(
                    self,
                    key,
                    _ConfigNode(value, self, self._key_path + [key], self._root),
                )

            # save and notify signal on root
            if self._root:
                self._root._on_change(self._key_path + [key], value)
        else:
            raise AttributeError("Cannot set attribute on non-dict config node")

    def __getitem__(self, key):
        """Support dict-like access: config['system']['SILENT']"""
        return self._data[key]

    def __setitem__(self, key, value):
        """Support dict-like setting: config['system']['SILENT'] = True"""
        self.__setattr__(key, value)

    def get_all(self):
        """Return the raw data"""
        return self._data


class ConfigManager(Service):
    """Dynamic config manager with arbitrary nesting support."""

    @Signal
    def changed(self, key_path: object, new_value: object) -> None: ...

    def __init__(self):
        super().__init__()
        self._data = {}
        self._root_node = None
        self._modules = {}  # Store module nodes here
        self._load()
        self._ensure_directories()

    def _load(self):
        """Load config from file, merge with defaults"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                    self._data = self._deep_merge(DEFAULTS.copy(), loaded_data)
            except Exception as e:
                print(f"Error loading config.json: {e}")
                self._data = DEFAULTS.copy()
        else:
            self._data = DEFAULTS.copy()
            self._save()

        # root node wrapper
        self._root_node = _ConfigNode(self._data, None, [], self)

        # store module nodes in a dict instead of as direct attributes
        self._modules = {}
        for key in self._data.keys():
            if isinstance(self._data[key], dict):
                self._modules[key] = _ConfigNode(
                    self._data[key], self._root_node, [key], self
                )

    def _deep_merge(self, base, updates):
        """Recursively merge updates into base"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _save(self):
        """Save config to file"""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self._data, f, indent=4)
        except Exception as e:
            print(f"Error saving config.json: {e}")

    def __getattr__(self, key):
        """Allow access to top-level config modules like config.system"""
        if key.startswith("_"):
            raise AttributeError(f"No attribute '{key}'")

        if key in self._modules:
            return self._modules[key]

        raise AttributeError(f"Config has no module '{key}'")

    def _on_change(self, key_path, value):
        """Called when any config value changes"""
        self._save()
        self.changed(key_path, value)

    def get(self, *path):
        """Get a value by path: config.get('system', 'SILENT')"""
        data = self._data
        for key in path:
            data = data[key]
        return data

    def set(self, *path, value):
        """Set a value by path: config.set('system', 'SILENT', value=True)"""
        data = self._data
        for key in path[:-1]:
            data = data[key]
        data[path[-1]] = value
        self._on_change(list(path), value)

    def reload(self):
        """Reload config from disk"""
        self._load()

    def get_all(self):
        """Get all config data as a dict"""
        return self._data.copy()

    def _ensure_directories(self):
        """Creates necessary system and configured directories if they don't exist."""
        # System/Cache Directories
        for directory in [TEMP_DIR, CACHE_DIR, CONFIG_DIR]:
            path = Path(directory).expanduser()
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                print(f"Created system directory: {path}")

        # Config Directories
        user_paths = self._data.get("paths", {})
        for key, folder_path in user_paths.items():
            if isinstance(folder_path, str):
                path = Path(folder_path).expanduser()
                if not path.exists():
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        print(f"Created configured directory: {path}")
                    except Exception as e:
                        print(f"Warning: Could not create {path}: {e}")

    # --- Convenience Properties ---

    @property
    def SILENT(self):
        return self.system.SILENT

    @SILENT.setter
    def SILENT(self, value):
        self.system.SILENT = value

    @property
    def VERTICAL(self):
        return self.system.VERTICAL

    @VERTICAL.setter
    def VERTICAL(self, value):
        self.system.VERTICAL = value

    @property
    def BRIGHTNESS_DEV(self):
        return self.system.BRIGHTNESS_DEV

    @BRIGHTNESS_DEV.setter
    def BRIGHTNESS_DEV(self, value):
        self.system.BRIGHTNESS_DEV = value

    @property
    def SCRIPTS_DIR(self):
        return self.paths.SCRIPTS_DIR

    @SCRIPTS_DIR.setter
    def SCRIPTS_DIR(self, value):
        self.paths.SCRIPTS_DIR = value

    @property
    def BAR_HEIGHT(self):
        return self.bar.HEIGHT

    @BAR_HEIGHT.setter
    def BAR_HEIGHT(self, value):
        self.bar.HEIGHT = value

    @property
    def WALLPAPERS_DIR(self):
        return self.paths.WALLPAPERS_DIR

    @WALLPAPERS_DIR.setter
    def WALLPAPERS_DIR(self, value):
        self.paths.WALLPAPERS_DIR = value

    @property
    def ALLOWED_PLAYERS(self):
        return self.system.ALLOWED_PLAYERS

    @ALLOWED_PLAYERS.setter
    def ALLOWED_PLAYERS(self, value):
        self.system.ALLOWED_PLAYERS = value


config = ConfigManager()
