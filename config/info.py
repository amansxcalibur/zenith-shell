import os
from pathlib import Path

from gi.repository import GLib  # type: ignore

SHELL_NAME = "zenith"
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename

WAYLAND_DISPLAY = os.environ.get("WAYLAND_DISPLAY")
XDG_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "").lower()
IS_WAYLAND = bool(WAYLAND_DISPLAY) or XDG_SESSION_TYPE == "wayland"

TEMP_DIR = f"/tmp/{SHELL_NAME}-shell"
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser(f"{GLib.get_user_cache_dir()}/{SHELL_NAME}-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DATA_DIR = os.path.expanduser(f"{ROOT_DIR}/data/")
