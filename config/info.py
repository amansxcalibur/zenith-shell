import os
from pathlib import Path

SHELL_NAME = "zenith-shell"
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename

TEMP_DIR = "/tmp/zenith"
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser("~/.cache/zenith-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
