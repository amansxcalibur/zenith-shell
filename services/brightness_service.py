import os
from loguru import logger
from gi.repository import Gio

from fabric.core.service import Service, Signal
from fabric.utils.helpers import monitor_file, exec_shell_command_async

from config.info import config


class BrightnessService(Service):
    _instance = None

    @Signal
    def value_changed(self, new_value: int, max_value: int) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()

        self.brightness = -1
        self.max_brightness = -1
        self.brightness_monitor = None
        self.backlight_path = f"/sys/class/backlight/{config.BRIGHTNESS_DEV}"

        try:
            self.brightness = self._read_brightness()
            self.max_brightness = self._read_max_brightness()
            self.brightness_monitor = monitor_file(self.backlight_path)
            self.brightness_monitor.connect("changed", self._on_brightness_changed)
            # emit
            self.value_changed(self.brightness, self.max_brightness)
        except Exception as e:
            logger.error(f"Brightness device not found at {self.backlight_path}: {e}")

    def _read_brightness(self) -> int:
        brightness_path = os.path.join(self.backlight_path, "brightness")
        if os.path.exists(brightness_path):
            with open(brightness_path) as f:
                return int(f.readline().strip())
        return -1

    def _read_max_brightness(self) -> int:
        max_path = os.path.join(self.backlight_path, "max_brightness")
        if os.path.exists(max_path):
            with open(max_path) as f:
                return int(f.readline())
        return -1

    def _on_brightness_changed(self, monitor: Gio.FileMonitor, file: Gio.File, *args):
        try:
            raw = file.load_bytes()[0].get_data()
            new_value = round(int(raw))
            self.brightness = new_value
            self.value_changed(new_value, self.max_brightness)
        except Exception as e:
            logger.warning(f"Failed to read brightness: {e}")

    def get_brightness(self) -> int:
        return self.brightness

    def get_max_brightness(self) -> int:
        return self.max_brightness

    def set_brightness(self, percent: int):
        percent = max(0, min(100, int(percent)))
        exec_shell_command_async(f"brightnessctl set {percent}%")

    def increment_brightness(self):
        exec_shell_command_async(["brightnessctl", "set", "+5%"])

    def decrement_brightness(self):
        exec_shell_command_async(["brightnessctl", "set", "5%-"])
