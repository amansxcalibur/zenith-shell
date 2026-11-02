import builtins

from fabric import Application
from fabric.utils import get_relative_path, monitor_file

from config.info import SHELL_NAME, ROOT_DIR
from .window import SettingsWindow

from gi.repository import Gio, GLib  # type: ignore


def main():
    import setproctitle

    setproctitle.setproctitle(SHELL_NAME + "-settings")
    GLib.set_prgname(SHELL_NAME + "-settings")

    app = Application(f"{SHELL_NAME}-settings", open_inspector=False)

    win = SettingsWindow()
    # `fabric-cli exec` evaluates in the outermost frame's globals, which under
    # `python -m settings` is runpy's, so expose via builtins to make it visible.
    builtins.settings_window = win
    win.show_all()
    app.add_window(win)

    def load_css(monitor_file, file, other_file, event_type):
        # no unnecessary bombardment in this house
        if event_type != Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            return

        app.set_stylesheet_from_file(
            get_relative_path("../main.css"),
            # feast on juggad
            exposed_functions={
                "mute_slider_img": lambda: (
                    f"background-image: url('{ROOT_DIR}/icons/mute.png');"
                ),
                "volume_slider_img": lambda: (
                    f"background-image: url('{ROOT_DIR}/icons/volume.png');"
                ),
                "brightness_slider_img": lambda: (
                    f"background-image: url('{ROOT_DIR}/icons/brightness.png');"
                ),
                "mic_slider_img": lambda: (
                    f"background-image: url('{ROOT_DIR}/icons/mic.svg');"
                ),
                "mic_off_slider_img": lambda: (
                    f"background-image: url('{ROOT_DIR}/icons/mic_off.svg');"
                ),
            },
        )

    app.style_monitor = monitor_file(get_relative_path("../styles"))
    app.style_monitor.connect("changed", load_css)
    load_css(None, None, None, Gio.FileMonitorEvent.CHANGES_DONE_HINT)

    app.run()


if __name__ == "__main__":
    main()
