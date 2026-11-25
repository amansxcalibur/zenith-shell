import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore

HEIGHT_RATIO = 0.75
ASPECT_RATIO = 1.42


def fit_to_monitor(dialog: Gtk.FileChooserDialog, shell_window: Gtk.Window) -> None:
    display = Gdk.Display.get_default()
    monitor = display.get_monitor_at_window(shell_window.get_window()).get_geometry()
    height = int(monitor.height * HEIGHT_RATIO)
    width = min(int(height * ASPECT_RATIO), monitor.width)
    # hyprland needs the first, sway the second
    for signal in ("realize", "map"):
        dialog.connect_after(signal, lambda d: d.resize(width, height))
