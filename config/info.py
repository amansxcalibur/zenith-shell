import os
from pathlib import Path

SHELL_NAME = "zenith"
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename

TEMP_DIR = f"/tmp/{SHELL_NAME}-shell"
HOME_DIR = os.path.expanduser("~")
CACHE_DIR = os.path.expanduser(f"~/.cache/{SHELL_NAME}-shell")
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = os.path.expanduser(f"{ROOT_DIR}/config/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
