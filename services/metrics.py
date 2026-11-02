import os
import re
import psutil
from loguru import logger

from fabric.core.service import Service, Signal

from gi.repository import GLib  # type: ignore

HWMON_DIR = "/sys/class/hwmon"
CPU_TEMP_SENSORS = ("coretemp", "k10temp")  # Intel, AMD; in order of preference


# I hate that this was causing frame drops for the Pill transitions...
def _find_cpu_temp_input() -> str | None:
    """Locate the CPU package temperature file (temp1 = "Package id 0"/Tctl).

    psutil.sensors_temperatures() reads *every* hwmon sensor, and some drivers
    are slow (an NVMe drive can take ~45ms). Called every second on the main
    loop, that froze the shell (~60ms+) and dropped animation frames.
    """
    found = {}
    try:
        entries = sorted(os.listdir(HWMON_DIR))
    except OSError:
        return None
    for entry in entries:
        path = os.path.join(HWMON_DIR, entry)
        try:
            with open(os.path.join(path, "name")) as f:
                name = f.read().strip()
        except OSError:
            continue
        temp_input = os.path.join(path, "temp1_input")
        if name in CPU_TEMP_SENSORS and name not in found and os.path.exists(temp_input):
            found[name] = temp_input
    return next((found[n] for n in CPU_TEMP_SENSORS if n in found), None)


class MetricsProvider(Service):
    _instance = None
    _initialized = False

    @Signal
    def battery_changed(self, percent: float, charging: bool) -> None: ...

    @Signal
    def metrics_changed(self, cpu: float, mem: float, disk: float) -> None: ...

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

        self.cpu: float = 0.0
        self.mem: float = 0.0
        self.disk: float = 0.0
        self.bat_percent: float = -1.0
        self.bat_charging: bool | None = None

        self._cpu_brand: str = self._read_cpu_brand()

        GLib.timeout_add_seconds(1, self._update)

        self._initialized = True

    @staticmethod
    def _read_cpu_brand() -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return re.sub(r".*model name.*:", "", line, count=1).strip()
        except Exception:
            logger.error("Failed read cpu info")
        return "Unknown CPU"

    def _update(self) -> bool:
        new_cpu = psutil.cpu_percent(interval=0)
        new_mem = psutil.virtual_memory().percent
        new_disk = psutil.disk_usage("/").percent
        if (new_cpu, new_mem, new_disk) != (self.cpu, self.mem, self.disk):
            self.cpu, self.mem, self.disk = new_cpu, new_mem, new_disk
            self.metrics_changed(self.cpu, self.mem, self.disk)

        battery = psutil.sensors_battery()
        if battery is None:
            self.bat_percent = 0.0
            self.bat_charging = None
        else:
            if (
                battery.percent != self.bat_percent
                or battery.power_plugged != self.bat_charging
            ):
                self.bat_percent = battery.percent
                self.bat_charging = battery.power_plugged
                self.battery_changed(self.bat_percent, self.bat_charging)

        return True

    def get_metrics(self) -> tuple[float, float, float]:
        return self.cpu, self.mem, self.disk

    def get_battery(self) -> tuple[float, bool | None]:
        return self.bat_percent, self.bat_charging

    _cpu_temp_path: str | None = None
    _cpu_temp_resolved = False

    @classmethod
    def get_cpu_temp(cls) -> str:
        # resolve once; then a single tiny sysfs read per call (well under 1ms)
        if not cls._cpu_temp_resolved:
            cls._cpu_temp_path = _find_cpu_temp_input()
            cls._cpu_temp_resolved = True
            if cls._cpu_temp_path is None:
                logger.warning("No coretemp/k10temp sensor found; CPU temp will be N/A")
        if cls._cpu_temp_path is None:
            return "N/A"
        try:
            with open(cls._cpu_temp_path) as f:
                return f"{int(f.read()) / 1000:.0f}C"
        except (OSError, ValueError):
            return "N/A"

    @staticmethod
    def get_disk_usage_gb() -> tuple[float, float]:
        usage = psutil.disk_usage("/")
        return usage.used / 1024**3, usage.total / 1024**3

    @staticmethod
    def get_mem_usage_gb() -> tuple[float, float]:
        usage = psutil.virtual_memory()
        return usage.used / 1024**3, usage.total / 1024**3
