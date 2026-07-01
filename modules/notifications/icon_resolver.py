import os
import re
import json
from loguru import logger

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


#TODO WIP


CACHE_DIR = str(GLib.get_user_cache_dir()) + "/fabric"
ICON_CACHE_FILE = CACHE_DIR + "/icons.json"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

class IconResolver:
    def __init__(self):
        if os.path.exists(ICON_CACHE_FILE):
            with open(ICON_CACHE_FILE) as f:
                try:
                    self._icon_dict = json.load(f)
                except json.JSONDecodeError:
                    logger.info("[ICONS] Cache file does not exist or is corrupted")
                    self._icon_dict = {}
        else:
            self._icon_dict = {}

    def get_icon(self, app_id: str) -> str:
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        logger.info(f"[ICONS] found new icon: '{new_icon}' for app id: '{app_id}', storing...")
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def _store_new_icon(self, app_id: str, icon: str) -> None:
        self._icon_dict[app_id] = icon
        with open(ICON_CACHE_FILE, "w") as f:
            json.dump(self._icon_dict, f)

    def _get_icon_from_desktop_file(self, desktop_file_path: str) -> str:
        in_desktop_entry = False
        with open(desktop_file_path) as f:
            for line in f:
                line = line.strip()
                if line == "[Desktop Entry]":
                    in_desktop_entry = True
                    continue
                if line.startswith("["):
                    in_desktop_entry = False
                    continue
                if in_desktop_entry and line.startswith("Icon="):
                    return line[5:].strip()
        return "application-x-symbolic"

    def _get_desktop_file(self, app_id: str) -> str | None:
        data_dirs = GLib.get_system_data_dirs()
        for data_dir in data_dirs:
            data_dir = data_dir + "/applications/"
            if os.path.exists(data_dir):
                files = os.listdir(data_dir)
                matching = [s for s in files if "".join(app_id.lower().split()) in s.lower()]
                if matching:
                    return data_dir + matching[0]
                for word in list(filter(None, re.split(r"-|\.|_|\s", app_id))):
                    matching = [s for s in files if word.lower() in s.lower()]
                    if matching:
                        return data_dir + matching[0]
        return None

    def _compositor_find_icon(self, app_id: str) -> str:
        desktop_file = self._get_desktop_file(app_id)
        if desktop_file:
            return self._get_icon_from_desktop_file(desktop_file)
        # return app_id as-is — Gtk.Image.new_from_icon_name will handle
        # it gracefully at render time when the main loop is running
        return app_id