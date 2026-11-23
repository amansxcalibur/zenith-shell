import os
import pwd
from pathlib import Path

from gi.repository import GLib  # type: ignore

from wm.detect import BACKENDS, bootstrap_wm

SHELL_NAME = "zenith"
USERNAME = pwd.getpwuid(os.getuid()).pw_name
HOSTNAME = os.uname().nodename

WAYLAND_DISPLAY = os.environ.get("WAYLAND_DISPLAY")
XDG_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "").lower()
BOOTSTRAP_WM = bootstrap_wm()
IS_WAYLAND = (
    BACKENDS[BOOTSTRAP_WM][0] == "wayland"
    if BOOTSTRAP_WM in BACKENDS
    else bool(WAYLAND_DISPLAY) or XDG_SESSION_TYPE == "wayland"
)

TEMP_DIR = os.path.join(GLib.get_user_runtime_dir(), f"{SHELL_NAME}-shell")
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser(f"{GLib.get_user_cache_dir()}/{SHELL_NAME}-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
USER_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), f"{SHELL_NAME}-shell")
CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.json")
THEMES_DIR = os.path.join(USER_CONFIG_DIR, "themes")
DATA_DIR = os.path.expanduser(f"{ROOT_DIR}/data/")
