from fabric import Application
from fabric.utils import get_relative_path, monitor_file

from config.info import SHELL_NAME, ROOT_DIR
from settings.window import SettingsWindow

from gi.repository import GLib


def main():
    import setproctitle

    setproctitle.setproctitle(SHELL_NAME + "-settings")
    GLib.set_prgname(SHELL_NAME + "-settings")

    app = Application("material-icon-test", open_inspector=False)

    win = SettingsWindow()
    win.show_all()
    app.add_window(win)

    def load_css(*args):
        app.set_stylesheet_from_file(
            get_relative_path("../main.css"),
            # feast on juggad
            exposed_functions={
                "mute_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/mute.png');",
                "volume_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/volume.png');",
                "brightness_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/brightness.png');",
            },
        )

    app.style_monitor = monitor_file(get_relative_path("../styles"))
    app.style_monitor.connect("changed", load_css)
    load_css()

    app.run()


if __name__ == "__main__":
    main()
