from loguru import logger
from typing import Optional, Any

from .common import DeviceStatus, ConnectionType, NetworkDevice

import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except ValueError:
    logger.error("Failed to load NetworkManager bindings")
    raise


class EthernetDevice(NetworkDevice):
    CONNECTION_TYPE = ConnectionType.ETHERNET

    def __init__(
        self,
        device: NM.DeviceEthernet,
        client: NM.Client
    ) -> None:
        super().__init__(device)
        self.client = client
        self._sig_ids["product"] = device.connect(
            "notify::product", self._on_ethernet_product_ready
        )
        self._sig_ids["state-changed"] = device.connect(
            "state-changed", self._on_device_state_change
        )

        # init
        self._update_connection_state(device.get_state())

    def connect_to_network(self) -> bool:
        if not self.device:
            logger.error("Cannot connect: no Ethernet device")
            return False

        if not self.client:
            logger.error("Cannot connect: no NM client")
            return False

        iface = self.device.get_iface()

        try:
            # find existing profile for the device
            existing = self._find_connection_profile()

            if existing:
                logger.info(f"Activating existing profile for {iface}")
                self.client.activate_connection_async(
                    existing,
                    self.device,
                    None,  # specific_object (AP path for wifi, None for ethernet)
                    None,  # cancellable
                    self._on_activate_complete,
                    iface,
                )
            else:
                logger.info(f"No profile found for {iface}, creating one")
                connection = self._create_connection_profile()
                self.client.add_and_activate_connection_async(
                    connection,
                    self.device,
                    None,  # specific_object
                    None,  # cancellable
                    self._on_activate_complete,
                    iface,
                )
            return True

        except Exception as e:
            logger.error(f"Failed to connect {iface}: {e}")
            return False

    def _find_connection_profile(self) -> Optional[NM.Connection]:
        if not self.client or not self.device:
            return None

        iface = self.device.get_iface()
        hw_addr = self.device.get_hw_address()

        for conn in self.client.get_connections():
            s_conn = conn.get_setting_connection()
            if not s_conn or s_conn.get_connection_type() != "802-3-ethernet":
                continue

            # match by interface name binding
            if s_conn.get_interface_name() == iface:
                return conn

            # or by hardware address binding
            s_wired = conn.get_setting_wired()
            if s_wired and s_wired.get_mac_address() == hw_addr:
                return conn

        return None

    def _create_connection_profile(self) -> NM.SimpleConnection:
        """Build a minimal Ethernet connection profile for this device."""
        connection = NM.SimpleConnection.new()

        s_conn = NM.SettingConnection.new()
        s_conn.set_property(NM.SETTING_CONNECTION_ID, self._ethernet_display_name(self.device))
        s_conn.set_property(NM.SETTING_CONNECTION_TYPE, "802-3-ethernet")
        # bind to this interface so NM doesn't reuse it on other ports
        s_conn.set_property(NM.SETTING_CONNECTION_INTERFACE_NAME, self.device.get_iface())

        s_wired = NM.SettingWired.new()
        s_ipv4 = NM.SettingIP4Config.new()
        s_ipv4.set_property(NM.SETTING_IP_CONFIG_METHOD, "auto")  # DHCP
        s_ipv6 = NM.SettingIP6Config.new()
        s_ipv6.set_property(NM.SETTING_IP_CONFIG_METHOD, "auto")

        connection.add_setting(s_conn)
        connection.add_setting(s_wired)
        connection.add_setting(s_ipv4)
        connection.add_setting(s_ipv6)

        return connection

    def _on_activate_complete(
        self, client: NM.Client, result: Any, iface: str
    ) -> None:
        try:
            active_conn = client.activate_connection_finish(result)
            if active_conn:
                logger.info(f"Ethernet connected: {iface}")
            else:
                logger.error(f"Ethernet activation returned no connection: {iface}")
        except Exception as e:
            logger.error(f"Ethernet activation failed for {iface}: {e}")
    
    def disconnect_network(self) -> bool:
        if not self.device:
            logger.error("Cannot disconnect: no Ethernet device")
            return False

        active_conn = self.get_active_connection()
        if not active_conn:
            logger.warning("No active connection to disconnect")
            return False

        if not self.client:
            logger.error("Cannot disconnect: no NM client")
            return False

        try:
            self.client.deactivate_connection_async(active_conn, None, None, None)
            logger.info(f"Disconnecting {self._ethernet_display_name(self.device)}")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False

    def _on_ethernet_product_ready(self, device: NM.DeviceEthernet, pspec: Any) -> None:
        product = device.get_product()
        if not product:
            return

        logger.debug(f"Product resolved for {device.get_iface()}: {product}")
        self._update_connection_state(device.get_state())

    def _on_device_state_change(
        self, device: NM.DeviceEthernet, new_state: int, old_state: int, reason: int
    ) -> None:
        logger.debug(
            f"Device {self._ethernet_display_name(device)} state changed: {old_state} -> {new_state} (reason: {reason})"
        )
        self._update_connection_state(new_state)

    def _update_connection_state(self, new_state: Optional[int] = None) -> None:
        dev = self.device
        if not dev:
            self._emit_state(DeviceStatus.NO_DEVICE, "Unknown")
            return

        if new_state is None:
            new_state = dev.get_state()

        display_name = self._ethernet_display_name(dev)
        state = self._map_nm_state(new_state)

        self._emit_state(state, display_name)

    @staticmethod
    def _ethernet_display_name(dev: NM.DeviceEthernet) -> str:
        product = dev.get_product()
        if product:
            return product
        active_conn = dev.get_active_connection()
        if active_conn:
            return active_conn.get_id()
        return dev.get_iface() or "Wired"

    def _emit_state(self, status: DeviceStatus, name: str) -> None:
        self.state = status
        self.state_changed(name, status)

    # helper pass-throughs
    def get_path(self) -> Optional[str]:
        return self.device.get_path() if self.device else None

    def get_iface(self) -> Optional[str]:
        return self.device.get_iface() if self.device else None

    def get_state(self) -> int:
        return self.device.get_state() if self.device else NM.DeviceState.UNKNOWN

    def get_product(self) -> Optional[str]:
        return self.device.get_product() if self.device else None

    def get_active_connection(self):
        return self.device.get_active_connection() if self.device else None
