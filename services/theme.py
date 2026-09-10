from fabric.core.service import Service, Signal
from fabric.utils.helpers import monitor_file

from config.info import ROOT_DIR


class ThemeService(Service):
    _instance = None

    @Signal
    def colors_changed(self) -> None: ...

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self.style_monitor = monitor_file(f"{ROOT_DIR}/styles/colors.css")
        self.style_monitor.connect("changed", lambda *_: self.colors_changed())

        self._initialized = True
