import os
import pwd
from pathlib import Path

from gi.repository import GLib  # type: ignore

SHELL_NAME = "zenith"
USERNAME = pwd.getpwuid(os.getuid()).pw_name
HOSTNAME = os.uname().nodename

WAYLAND_DISPLAY = os.environ.get("WAYLAND_DISPLAY")
XDG_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "").lower()
# the installer sets this to write one WM's config from any session (see config.bootstrap)
BOOTSTRAP_WM = os.environ.get("ZENITH_BOOTSTRAP_WM")
IS_WAYLAND = (
    BOOTSTRAP_WM == "sway"
    if BOOTSTRAP_WM
    else bool(WAYLAND_DISPLAY) or XDG_SESSION_TYPE == "wayland"
)

TEMP_DIR = os.path.join(GLib.get_user_runtime_dir(), f"{SHELL_NAME}-shell")
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser(f"{GLib.get_user_cache_dir()}/{SHELL_NAME}-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
USER_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), f"{SHELL_NAME}-shell")
CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.json")
DATA_DIR = os.path.expanduser(f"{ROOT_DIR}/data/")
