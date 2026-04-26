from loguru import logger
from typing import Optional, Any

from fabric.core.service import Service, Signal, Property

from config.config import config

from .wifi import WifiDevice
from .common import ConnectionType
from .ethernet import EthernetDevice

import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM, GLib, GObject
except ValueError:
    logger.error("Failed to load NetworkManager bindings")
    raise


class NetworkService(Service):
    @Signal
    def primary_connection_change(self, device: object) -> None:
        """Emitted when primary connection status changes"""
        ...

    @Signal
    def ethernet_change(self) -> None:
        """Emitted when available ethernet list updates"""
        ...

    @Property(bool, default_value=False, flags="readable")
    def wifi_enabled(self) -> bool:
        return self.client.wireless_get_enabled() if self.client else False

    def __init__(self):
        super().__init__()

        self.client: Optional[NM.Client] = None
        self.wifi_dev: Optional[WifiDevice] = None
        self.ethernet_devs: dict[str, EthernetDevice] = {}

        self._init_client()

    def _init_client(self) -> None:
        try:
            self.client = NM.Client.new(None)
            if not self.client:
                logger.error("Failed to create NM Client")
                return

            self.client.connect("device-added", self._on_device_added)
            self.client.connect("device-removed", self._on_device_removed)
            self.client.connect(
                "notify::primary-connection", self._on_primary_connection_changed
            )

            for dev in self.client.get_devices() or []:
                if dev.get_device_type() == NM.DeviceType.WIFI and not self.wifi_dev:
                    # only track first WiFi device
                    self._init_wifi_device(dev)
                elif dev.get_device_type() == NM.DeviceType.ETHERNET:
                    # track ALL Ethernet devices
                    self._register_ethernet_device(dev)

            GLib.idle_add(self._initialize_state)

        except Exception as e:
            logger.error(f"Failed to initialize NetworkManager client: {e}")

    def _register_ethernet_device(
        self, device: NM.DeviceEthernet
    ) -> Optional[EthernetDevice]:
        if not device:
            return
        path = device.get_path()
        if path is None:
            return
        if path in self.ethernet_devs:
            # destroy and recreate/rewire instead of returning????
            # # already tracked, update underlying device reference
            # try:
            #     self.ethernet_devs[path].update_device(device)
            # except Exception:
            #     pass
            return self.ethernet_devs[path]

        try:
            dev_wrapper = EthernetDevice(device, self.client)
            self.ethernet_devs[path] = dev_wrapper
            logger.info(f"Ethernet device registered: {device.get_iface()}")
            return dev_wrapper
        except Exception as e:
            logger.error(f"Failed to register Ethernet device: {e}")
            return None

    def _unregister_ethernet_device(self, path: str) -> Optional[NM.DeviceEthernet]:
        dev_wrapper = self.ethernet_devs.pop(path, None)
        if dev_wrapper is not None:
            logger.info(f"Ethernet device unregistering: {dev_wrapper.get_iface()}")
            dev_wrapper.destroy()

    def _init_wifi_device(self, device: NM.DeviceWifi) -> Optional[WifiDevice]:
        if not device:
            logger.error("Cannot initialize: device is None")
            return

        if self.wifi_dev:
            self.wifi_dev.destroy()  # sorry :(

        try:
            dev_wrapper = WifiDevice(device, self.client)
            self.wifi_dev = dev_wrapper
            logger.info(f"WiFi device found: {device.get_iface()}")
            return dev_wrapper

        except Exception as e:
            logger.error(f"Failed to initialize WiFi device: {e}")
            self.wifi_dev = None
            return None

    def _initialize_state(self) -> bool:
        self._on_primary_connection_changed(self.client, None)
        self.toggle_wifi_radio(enabled=config.network.wifi.enabled)
        return False  # don't repeat

    @staticmethod
    def _conn_type_from_primary(primary: NM.ActiveConnection) -> ConnectionType:
        devs = primary.get_devices()
        if not devs:
            return ConnectionType.NONE

        dev = devs[0]
        if isinstance(dev, NM.DeviceEthernet):
            return ConnectionType.ETHERNET
        if isinstance(dev, NM.DeviceWifi):
            return ConnectionType.WIFI
        return ConnectionType.NONE

    def _on_primary_connection_changed(self, client: NM.Client, pspec: Any) -> None:
        primary_conn = client.get_primary_connection()
        if not primary_conn:
            logger.info("No primary connection (offline?)")
            self.primary_connection_change(None)
            return

        devs = primary_conn.get_devices()
        if not devs:
            return

        dev_wrapper = None
        dev = devs[0]

        if isinstance(dev, NM.DeviceEthernet):
            dev_wrapper = self._register_ethernet_device(dev)
            logger.debug(f"Ethernet device updated: {dev.get_iface()}")

        elif isinstance(dev, NM.DeviceWifi):
            if not self.wifi_dev or dev.get_path() != self.wifi_dev.get_path():
                dev_wrapper = self._init_wifi_device(dev)
            else:
                dev_wrapper = self.wifi_dev

        self.primary_connection_change(dev_wrapper)
        logger.info(
            f"Primary connection -> {self._conn_type_from_primary(primary_conn)}"
        )

    def get_wifi_device(self) -> Optional[WifiDevice]:
        return self.wifi_dev

    def get_ethernet_list(self) -> list[dict]:
        if self.client is None:
            return []
        return [
            {
                "name": EthernetDevice._ethernet_display_name(device),
                "state": device.get_state(),
                "iface": device.get_iface(),
                "device": device,
            }
            for device in self.ethernet_devs.values()
        ]

    def toggle_wifi_radio(self, enabled: Optional[bool] = None) -> bool:
        # enabled: True(enable), False(disable), None(toggle)
        if not self.client:
            logger.error("Cannot toggle WiFi: no client")
            return False

        try:
            current = self.client.wireless_get_enabled()
            new_state = not current if enabled is None else enabled

            logger.info(f"Setting WiFi radio: {new_state}")
            self.client.wireless_set_enabled(new_state)
            return True

        except Exception as e:
            logger.error(f"Failed to toggle WiFi: {e}")
            return False

    def _on_device_added(self, client: NM.Client, device: NM.Device) -> None:
        if not device:
            return

        logger.debug(f"Device detected: {device.get_device_type()}")

        dev_type = device.get_device_type()
        if dev_type == NM.DeviceType.WIFI and not self.wifi_dev:
            logger.info("WiFi device added")
            self._init_wifi_device(device)

        elif dev_type == NM.DeviceType.ETHERNET:
            path = device.get_path()
            if path is None or path == "/":
                logger.debug("Ethernet path not ready, waiting...")
                handler_id = None

                def on_path_ready(dev, pspec):
                    nonlocal handler_id  # outer scope
                    if dev.get_path() not in [None, "/"]:
                        if handler_id is not None:
                            GObject.Object.disconnect(dev, handler_id)

                        self._register_ethernet_device(dev)
                        self.ethernet_change()

                handler_id = device.connect("notify::path", on_path_ready)
                return

            self._register_ethernet_device(device)
            logger.info("Ethernet device added")
            self.ethernet_change()

    def _on_device_removed(self, client: NM.Client, device: NM.Device) -> None:
        if not device:
            return

        logger.debug(f"Removing device: {device.get_device_type()}")
        try:
            dev_path = device.get_path()
            if self.wifi_dev and dev_path == self.wifi_dev.get_path():
                # detach signals and clear wrapper
                try:
                    self.wifi_dev.destroy()
                except Exception:
                    pass
                self.wifi_dev = None
                logger.info("WiFi device removed")

            elif dev_path in self.ethernet_devs:
                self._unregister_ethernet_device(dev_path)
                logger.info("Ethernet device removed")
                self.ethernet_change()

        except Exception as e:
            logger.error(f"Error handling device removed: {e}")
