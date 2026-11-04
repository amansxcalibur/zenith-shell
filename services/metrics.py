import os
import re
import time
import psutil
from typing import NamedTuple
from loguru import logger

from fabric.core.service import Service, Signal

from gi.repository import GLib  # type: ignore

HWMON_DIR = "/sys/class/hwmon"
CPU_TEMP_SENSORS = ("coretemp", "k10temp")  # Intel, AMD; in order of preference
# their traffic is already counted on a physical interface
VIRTUAL_NIC_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "vnet", "tun", "tap")


class IoRates(NamedTuple):
    """Bytes per second."""

    net_down: float = 0.0
    net_up: float = 0.0
    disk_read: float = 0.0
    disk_write: float = 0.0


class ProcessGroup(NamedTuple):
    """All running processes that share a name."""

    name: str
    cpu: float  # percent of the whole machine, comparable to overall CPU usage
    rss: int  # bytes; sums each process's RSS, so shared pages count repeatedly
    count: int


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
        if (
            name in CPU_TEMP_SENSORS
            and name not in found
            and os.path.exists(temp_input)
        ):
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
        self._io_counters = self._read_io_counters()
        self._io_time = time.monotonic()

        GLib.timeout_add_seconds(1, self._update)

        self._initialized = True

    @staticmethod
    def _read_cpu_brand() -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        name = line.split(":", 1)[1]
                        # "12th Gen Intel(R) Core(TM) i5 CPU @ 2.5GHz" -> "Intel Core i5"
                        name = re.sub(
                            r"^\s*\d+\w* Gen\b|\((R|TM)\)|\bCPU\b|@.*",
                            "",
                            name,
                            flags=re.IGNORECASE,
                        )
                        return " ".join(name.split())
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
    def get_cpu_temp(cls) -> float | None:
        # resolve once; then a single tiny sysfs read per call (well under 1ms)
        if not cls._cpu_temp_resolved:
            cls._cpu_temp_path = _find_cpu_temp_input()
            cls._cpu_temp_resolved = True
            if cls._cpu_temp_path is None:
                logger.warning("No coretemp/k10temp sensor found; CPU temp will be N/A")
        if cls._cpu_temp_path is None:
            return None
        try:
            with open(cls._cpu_temp_path) as f:
                return int(f.read()) / 1000
        except (OSError, ValueError):
            return None

    @staticmethod
    def get_disk_usage_gb() -> tuple[float, float]:
        usage = psutil.disk_usage("/")
        return usage.used / 1024**3, usage.total / 1024**3

    @staticmethod
    def get_per_cpu_usage() -> list[float]:
        return psutil.cpu_percent(percpu=True)

    @staticmethod
    def get_cpu_counts() -> tuple[int, int]:
        """(physical cores, logical threads); physical falls back to logical."""
        threads = psutil.cpu_count() or 1
        return psutil.cpu_count(logical=False) or threads, threads

    @staticmethod
    def get_mem_breakdown() -> tuple[int, int, int, int]:
        """(used, reclaimable cache, free, total) bytes; the first three sum to total.

        Used is total - available, which is what `percent` is derived from; `usage.used`
        isn't, and would disagree with the percentage shown next to it.
        """
        usage = psutil.virtual_memory()
        return (
            usage.total - usage.available,
            max(0, usage.available - usage.free),
            min(usage.free, usage.available),
            usage.total,
        )

    @staticmethod
    def get_swap() -> tuple[int, int]:
        """(used, total) bytes."""
        usage = psutil.swap_memory()
        return usage.used, usage.total

    @staticmethod
    def get_cpu_freq() -> tuple[float, float] | None:
        """(current, max) MHz averaged over CPUs, or None if unavailable."""
        freq = psutil.cpu_freq()
        return (freq.current, freq.max) if freq and freq.max else None

    @staticmethod
    def get_cpu_time_split() -> tuple[float, float, float]:
        """(user, system, iowait) percent since the previous call."""
        times = psutil.cpu_times_percent()
        return (
            times.user + getattr(times, "nice", 0.0),
            times.system,
            getattr(times, "iowait", 0.0),
        )

    @staticmethod
    def get_load_avg() -> tuple[float, float, float]:
        return os.getloadavg()

    @staticmethod
    def get_uptime() -> float:
        """Seconds since boot."""
        return time.time() - psutil.boot_time()

    @staticmethod
    def get_task_count() -> int:
        return len(psutil.pids())

    @staticmethod
    def _read_io_counters() -> tuple[int, int, int, int]:
        nics = psutil.net_io_counters(pernic=True)
        physical = [
            c for n, c in nics.items() if not n.startswith(VIRTUAL_NIC_PREFIXES)
        ]
        disk = psutil.disk_io_counters()
        return (
            sum(c.bytes_recv for c in physical),
            sum(c.bytes_sent for c in physical),
            disk.read_bytes if disk else 0,
            disk.write_bytes if disk else 0,
        )

    def get_io_rates(self) -> IoRates:
        """Network and disk throughput since the previous call."""
        counters = self._read_io_counters()
        now = time.monotonic()
        elapsed = max(now - self._io_time, 1e-3)
        rates = IoRates(
            *(
                max(0, new - old) / elapsed  # counters reset if a NIC goes away
                for new, old in zip(counters, self._io_counters, strict=True)
            )
        )
        self._io_counters, self._io_time = counters, now
        return rates

    @staticmethod
    def get_process_groups() -> list[ProcessGroup]:
        """Every process, grouped by name. Takes ~10ms: never call on the main loop."""
        threads = psutil.cpu_count() or 1
        groups: dict[str, list] = {}
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            info = proc.info
            group = groups.setdefault(info["name"] or "?", [0.0, 0, 0])
            group[0] += (info["cpu_percent"] or 0.0) / threads
            group[1] += info["memory_info"].rss if info["memory_info"] else 0
            group[2] += 1
        return [ProcessGroup(name, *group) for name, group in groups.items()]
