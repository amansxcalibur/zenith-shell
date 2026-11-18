import os
import struct
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from loguru import logger
from fabric.core.service import Service, Signal

from gi.repository import GLib  # type: ignore

# struct rfkill_event (v1): idx u32, type u8, op u8, soft u8, hard u8
EVENT = struct.Struct("=IBBBB")

TYPE_ALL = 0
TYPE_WLAN = 1
TYPE_BLUETOOTH = 2

OP_ADD = 0
OP_DEL = 1
OP_CHANGE = 2
OP_CHANGE_ALL = 3


class RfkillService(Service):
    """Watches /dev/rfkill for the radios' block states, and soft-blocks them."""

    _instance = None

    @Signal
    def changed(self) -> None: ...

    @property
    def available(self) -> bool:
        return bool(self.devices)

    @property
    def all_blocked(self) -> bool:
        return self.available and all(
            soft or hard for _, soft, hard in self.devices.values()
        )

    @property
    def any_hard_blocked(self) -> bool:
        return any(hard for _, _, hard in self.devices.values())

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._initialized = True

        # idx -> (type, soft blocked, hard blocked)
        self.devices: dict[int, tuple[int, bool, bool]] = {}
        self.writable = False
        self._fd = None
        # the kernel holds its rfkill lock while drivers switch radios, which
        # *could* maybe take a while. We ain't freezing main loop for all dat
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rfkill")

        for flags, writable in ((os.O_RDWR, True), (os.O_RDONLY, False)):
            try:
                self._fd = os.open("/dev/rfkill", flags | os.O_NONBLOCK)
                self.writable = writable
                break
            except PermissionError:
                continue
            except OSError as e:
                logger.warning(f"[Rfkill] /dev/rfkill unavailable: {e}")
                return
        if self._fd is None:
            logger.warning("[Rfkill] no permission to read /dev/rfkill")
            return
        if not self.writable:
            logger.warning("[Rfkill] /dev/rfkill is read-only; can't toggle radios")

        self._read_events()  # opening it queues an ADD for every radio
        GLib.io_add_watch(
            GLib.IOChannel.unix_new(self._fd),
            GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN,
            self._on_readable,
        )

    def unblocked_types(self) -> set[int]:
        return {t for t, soft, hard in self.devices.values() if not (soft or hard)}

    def present_types(self) -> set[int]:
        return {t for t, _, _ in self.devices.values()}

    def set_blocked(
        self,
        radio_type: int,
        blocked: bool,
        on_failed: Callable[[], None] | None = None,
    ) -> bool:
        """Soft-block or unblock every radio of a type (TYPE_ALL for all)."""
        if self._fd is None or not self.writable:
            return False
        event = EVENT.pack(0, radio_type, OP_CHANGE_ALL, int(blocked), 0)
        self._writer.submit(self._write, event, on_failed)
        return True

    def _write(self, event: bytes, on_failed: Callable[[], None] | None):
        try:
            os.write(self._fd, event)
        except OSError as e:
            logger.error(f"[Rfkill] couldn't change radio state: {e}")
            if on_failed is not None:
                GLib.idle_add(lambda: on_failed() and False)

    def _read_events(self) -> bool:
        changed = False
        while True:
            try:
                data = os.read(self._fd, EVENT.size)
            except BlockingIOError:
                break
            except OSError as e:
                logger.error(f"[Rfkill] read failed: {e}")
                break
            if len(data) < EVENT.size:
                break
            idx, radio_type, op, soft, hard = EVENT.unpack(data)
            if op in (OP_ADD, OP_CHANGE):
                self.devices[idx] = (radio_type, bool(soft), bool(hard))
                changed = True
            elif op == OP_DEL:
                changed = self.devices.pop(idx, None) is not None or changed
        return changed

    def _on_readable(self, *_) -> bool:
        if self._read_events():
            self.changed()
        return True
