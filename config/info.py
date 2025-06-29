import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

ALLOWED_PLAYERS = ['vlc', 'cmus', 'firefox', 'spotify', 'chromium']
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = os.path.expanduser("~")
WALLPAPERS_DIR = os.path.expanduser("~/Pictures/Wallpapers/")
VERTICAL = False
print(USERNAME, HOSTNAME, HOME_DIR)
print(Gtk)
