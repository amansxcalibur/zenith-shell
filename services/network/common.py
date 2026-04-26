from loguru import logger
from enum import Enum, auto

from fabric.core.service import Service, Signal, Property

import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM, GObject
except ValueError:
    logger.error("Failed to load NetworkManager bindings")
    raise


class NetworkConstants:
    SCAN_DEBOUNCE_MS = 500
    CLEANUP_DELAY_MS = 500
    CONNECTION_TIMEOUT_SECONDS = 30
    MAX_SSID_LENGTH = 32


class ConnectionResult(Enum):
    SUCCESS = auto()
    PASSWORD_REQUIRED = auto()
    NETWORK_NOT_FOUND = auto()
    NO_DEVICE = auto()
    ALREADY_CONNECTED = auto()
    INVALID_PASSWORD = auto()
    CONNECTION_FAILED = auto()
    DEVICE_BUSY = auto()
    TIMEOUT = auto()


class DeviceStatus(Enum):
    DEVICE_OFF = "Device Off"
    DISCONNECTED = "Device On (No Connection)"
    CONNECTING = "Connecting…"
    CONNECTED = "Connected"
    NO_DEVICE = "No Device"
    FAILED = "Connection Failed"
    UNKNOWN = "Unknown"


class ConnectionType(Enum):
    NONE = 0
    WIFI = 1
    ETHERNET = 2


class NetworkDevice(Service):
    @Signal
    def state_changed(self, identifier: str, status: object) -> None: ...

    @Property(object, "read-write")
    def state(self) -> DeviceStatus:
        return self._state

    @state.setter
    def state(self, value: DeviceStatus):
        self._state = value

    def __init__(self, device: NM.Device):
        super().__init__()
        self.device = device
        self._state = DeviceStatus.UNKNOWN
        self._sig_ids: dict[str, int] = {}

    def _map_nm_state(self, nm_state: NM.DeviceState) -> DeviceStatus:
        match nm_state:
            case NM.DeviceState.UNAVAILABLE:
                return DeviceStatus.DEVICE_OFF
            case NM.DeviceState.DISCONNECTED:
                return DeviceStatus.DISCONNECTED
            case (
                NM.DeviceState.PREPARE
                | NM.DeviceState.CONFIG
                | NM.DeviceState.NEED_AUTH
                | NM.DeviceState.IP_CONFIG
                | NM.DeviceState.IP_CHECK
                | NM.DeviceState.SECONDARIES
            ):
                return DeviceStatus.CONNECTING
            case NM.DeviceState.ACTIVATED:
                return DeviceStatus.CONNECTED
            case NM.DeviceState.FAILED:
                return DeviceStatus.FAILED
            case _:
                return DeviceStatus.UNKNOWN

    def destroy(self) -> None:
        if self.device:
            for handler_id in self._sig_ids.values():
                # use the base class to avoid the NM.Device.disconnect(cancellable) collision
                # courtesy of NM for naming both functions the same :|
                if GObject.Object.handler_is_connected(self.device, handler_id):
                    GObject.Object.disconnect(self.device, handler_id)
            self._sig_ids.clear()
            self.device = None

        logger.debug("NetworkDevice cleaned up (Signals unhooked).")
