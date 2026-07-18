import os
import shutil

from fabric.core.service import Property, Signal, Service
from fabric.utils.helpers import get_relative_path


class ThemeManager(Service):
    _instance = None

    @Signal
    def mode_changed(self, mode: str) -> None: ...

    @Property(str, "readable")
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if self._mode == value:
            return
        self._apply(value)
        self._mode = value
        self.emit("mode-changed", value)

    def _apply(self, value: str):
        colors_path = get_relative_path("../styles/colors.css")
        source_path = get_relative_path(f"../data/colors.{value}.css")
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"No color cache for mode '{value}': {source_path}")
        shutil.copy(source_path, colors_path)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._mode = "light"
        self._apply(self._mode)  # sync colors.css on startup
        self._initialized = True
        
    def update_colors(self):
        self._apply(self._mode)
