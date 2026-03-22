import re
import psutil

from fabric.core.service import Service, Signal

from gi.repository import GLib

class MetricsProvider(Service):
    _instance = None
    _initialized = False

    @Signal
    def battery_changed(self, percent: float, charging: bool) -> None: ...

    @property
    def cpu_brand(self) -> str:
        return self._cpu_brand

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True

        self.cpu: float = 0.0
        self.mem: float = 0.0
        self.disk: float = 0.0
        self.bat_percent: float = -1.0
        self.bat_charging: bool | None = None

        self._cpu_brand: str = self._read_cpu_brand()

        GLib.timeout_add_seconds(1, self._update)

    @staticmethod
    def _read_cpu_brand() -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return re.sub(r".*model name.*:", "", line, count=1).strip()
        except Exception:
            pass
        return "Unknown CPU"

    def _update(self) -> bool:
        self.cpu = psutil.cpu_percent(interval=0)
        self.mem = psutil.virtual_memory().percent
        self.disk = psutil.disk_usage("/").percent

        battery = psutil.sensors_battery()
        if battery is None:
            self.bat_percent = 0.0
            self.bat_charging = None
        else:
            self.bat_percent = battery.percent
            self.bat_charging = battery.power_plugged
            self.battery_changed(self.bat_percent, self.bat_charging)

        return True

    def get_metrics(self) -> tuple[float, float, float]:
        return self.cpu, self.mem, self.disk

    def get_battery(self) -> tuple[float, bool | None]:
        return self.bat_percent, self.bat_charging

    @staticmethod
    def get_cpu_temp() -> str:
        temps = psutil.sensors_temperatures()
        if "coretemp" in temps:
            return f"{temps['coretemp'][0].current:.0f}C"
        if "k10temp" in temps:
            return f"{temps['k10temp'][0].current:.0f}C"
        return "N/A"

    @staticmethod
    def get_disk_usage_gb() -> tuple[float, float]:
        usage = psutil.disk_usage("/")
        return usage.used / 1024**3, usage.total / 1024**3

    @staticmethod
    def get_mem_usage_gb() -> tuple[float, float]:
        usage = psutil.virtual_memory()
        return usage.used / 1024**3, usage.total / 1024**3