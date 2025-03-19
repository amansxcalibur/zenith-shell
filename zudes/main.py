from fabric import Application
from fabric.utils import get_relative_path
from bar import Bar
from notch import Notch
# from modules.overview import Overview

if __name__ == "__main__":
    bar = Bar()
    notch = Notch()
    # overview = Overview()
    app = Application("ax-shell", bar, notch)
    app.set_stylesheet_from_file(get_relative_path("main.css"))

    app.run()