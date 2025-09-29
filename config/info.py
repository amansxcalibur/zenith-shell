import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

# meta
SHELL_NAME = 'bar-example'
ALLOWED_PLAYERS = ['vlc', 'cmus', 'firefox', 'spotify', 'chromium']
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
BRIGHTNESS_DEV = "intel_backlight"

# settings
SILENT = False
VERTICAL = False

# directories
HOME_DIR = os.path.expanduser("~")
WALLPAPERS_DIR = os.path.expanduser("~/Pictures/Wallpapers/")
CACHE_DIR = os.path.expanduser("/tmp")
SCRIPTS_DIR = os.path.expanduser("~/i3scripts")

print(USERNAME, HOSTNAME, HOME_DIR)
print(Gtk)
