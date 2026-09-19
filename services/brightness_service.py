import os
from loguru import logger
from gi.repository import Gio  # type: ignore

from fabric.core.service import Service, Signal
from fabric.utils.helpers import monitor_file, exec_shell_command_async

from config.config import config


class BrightnessService(Service):
    _instance = None

    BACKLIGHT_BASE_DIR = "/sys/class/backlight"

    @Signal
    def value_changed(self, new_value: int, max_value: int) -> None: ...

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self.brightness = -1
        self.max_brightness = -1
        self.brightness_monitor = None
        dev_name = config.BRIGHTNESS_DEV

        if dev_name == "auto":
            dev_name = self._get_backlight_device()

        if dev_name:
            self.backlight_path = os.path.join(self.BACKLIGHT_BASE_DIR, dev_name)
        else:
            self.backlight_path = None
            logger.error("No backlight device found")

        try:
            self.brightness = self._read_brightness()
            self.max_brightness = self._read_max_brightness()
            self.brightness_monitor = monitor_file(self.backlight_path + "/brightness")
            self.brightness_monitor.connect("changed", self._on_brightness_changed)
            # emit
            self.value_changed(self.brightness, self.max_brightness)
        except Exception as e:
            logger.error(f"Brightness device not found at {self.backlight_path}: {e}")

    def _get_backlight_device(self):
        if not os.path.exists(self.BACKLIGHT_BASE_DIR):
            return None

        devices = os.listdir(self.BACKLIGHT_BASE_DIR)
        if not devices:
            return None

        # Vendor-specific hardware drivers (intel, amd) are faster and more reliable than generic ACPI.
        vendor_devices = [d for d in devices if d != "acpi_video0"]
        return vendor_devices[0] if vendor_devices else devices[0]

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
        exec_shell_command_async("brightnessctl set +5%")

    def decrement_brightness(self):
        exec_shell_command_async("brightnessctl set 5%-")
