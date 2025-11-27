from loguru import logger
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable

from fabric.core.service import Service, Signal, Property

from config.info import config

import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM, GLib
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
    WIFI_OFF = "Wi-Fi Off"
    DISCONNECTED = "Wi-Fi On (No Connection)"
    CONNECTING = "Connecting…"
    CONNECTED = "Connected"
    NO_DEVICE = "No Device"
    FAILED = "Connection Failed"
    UNKNOWN = "Unknown"


@dataclass
class PendingConnection:
    """Represents a connection attempt in progress"""

    ssid: str
    active_conn: Any
    is_new: bool
    timestamp: int


@dataclass
class NetworkInfo:
    bssid: str
    ssid: str
    active: bool
    strength: int
    frequency: int
    flags: int
    wpa_flags: int
    rsn_flags: int
    secured: bool
    icon_name: str
    last_seen: int

    def to_dict(self) -> dict:
        return {
            "bssid": self.bssid,
            "ssid": self.ssid,
            "active": self.active,
            "strength": self.strength,
            "frequency": self.frequency,
            "flags": self.flags,
            "wpa_flags": self.wpa_flags,
            "rsn_flags": self.rsn_flags,
            "secured": self.secured,
            "icon-name": self.icon_name,
            "last_seen": self.last_seen,
        }


class SignalStrengthMapper:
    ICON_MAP = {
        80: "network-wireless-signal-excellent-symbolic",
        60: "network-wireless-signal-good-symbolic",
        40: "network-wireless-signal-ok-symbolic",
        20: "network-wireless-signal-weak-symbolic",
        0: "network-wireless-signal-none-symbolic",
    }

    @classmethod
    def get_icon(cls, strength: int) -> str:
        """Get appropriate icon for signal strength"""
        normalized = min(80, 20 * round(strength / 20))
        return cls.ICON_MAP.get(normalized, "network-wireless-no-route-symbolic")


class NetworkInfoFactory:
    @staticmethod
    def from_access_point(
        ap: NM.AccessPoint, active_ssid: Optional[str] = None
    ) -> Optional[NetworkInfo]:
        """Create NetworkInfo from NM.AccessPoint"""
        try:
            if not ap or not ap.get_ssid():
                return None

            ssid = NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
            strength = ap.get_strength()

            return NetworkInfo(
                bssid=ap.get_bssid(),
                ssid=ssid,
                active=active_ssid is not None and ssid == active_ssid,
                strength=strength,
                frequency=ap.get_frequency(),
                flags=ap.get_flags(),
                wpa_flags=ap.get_wpa_flags(),
                rsn_flags=ap.get_rsn_flags(),
                secured=ap.get_wpa_flags() != 0 or ap.get_rsn_flags() != 0,
                icon_name=SignalStrengthMapper.get_icon(strength),
                last_seen=ap.get_last_seen(),
            )
        except Exception as e:
            logger.debug(f"Error creating NetworkInfo: {e}")
            return None


class AccessPointManager:
    def __init__(self):
        self.ap_list: List[NM.AccessPoint] = []

    def update(self, new_list: List[NM.AccessPoint]) -> None:
        self.ap_list = new_list

    def get_unique_networks(
        self, active_ssid: Optional[str] = None
    ) -> List[NetworkInfo]:
        # deduplicate by SSID
        ap_dict: Dict[str, NM.AccessPoint] = {}

        for ap in self.ap_list:
            try:
                if not ap or not ap.get_ssid():
                    continue

                ssid = NM.utils_ssid_to_utf8(ap.get_ssid().get_data())

                # keep the strongest signal for each SSID
                if (
                    ssid not in ap_dict
                    or ap.get_strength() > ap_dict[ssid].get_strength()
                ):
                    ap_dict[ssid] = ap
            except Exception as e:
                logger.debug(f"Error processing AP: {e}")
                continue

        # convert to NetworkInfo objects
        networks = []
        for ap in ap_dict.values():
            if network := NetworkInfoFactory.from_access_point(ap, active_ssid):
                networks.append(network)

        # sort by signal strength
        networks.sort(key=lambda x: x.strength, reverse=True)

        return networks

    def find_by_ssid(self, ssid: str) -> Optional[NM.AccessPoint]:
        for ap in self.ap_list:
            try:
                if not ap or not ap.get_ssid():
                    continue

                ap_ssid = NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
                if ap_ssid == ssid:
                    return ap
            except Exception as e:
                logger.debug(f"Error checking AP SSID: {e}")
                continue

        return None


class ConnectionStateMachine:
    def __init__(self, network_service: "NetworkService"):
        self.network_service = network_service
        self.pending: Dict[str, PendingConnection] = {}

    def track_connection(self, ssid: str, active_conn: Any, is_new: bool) -> None:
        self.pending[ssid] = PendingConnection(
            ssid=ssid,
            active_conn=active_conn,
            is_new=is_new,
            timestamp=GLib.get_monotonic_time(),
        )

        GLib.timeout_add_seconds(
            NetworkConstants.CONNECTION_TIMEOUT_SECONDS, self._check_timeout, ssid
        )

        logger.debug(f"Tracking connection to {ssid} (new_profile={is_new})")

    def mark_success(self, ssid: str) -> None:
        if ssid in self.pending:
            logger.info(f"Connection to {ssid} succeeded")
            del self.pending[ssid]
            self.network_service.connection_result(
                ssid, ConnectionResult.SUCCESS, "Connected successfully"
            )

    def mark_failed(
        self, ssid: str, reason: ConnectionResult, message: str = ""
    ) -> None:
        if pending := self.pending.pop(ssid, None):
            logger.warning(f"Connection to {ssid} failed: {reason.name}")

            # cleanup new connection profiles that failed
            if pending.is_new:
                self._schedule_cleanup(ssid)

            self.network_service.connection_result(ssid, reason, message)

    def check_disconnected_state(self, current_ssid: Optional[str]) -> None:
        """Check if any pending connections failed when device disconnected"""
        for ssid in list(self.pending.keys()):
            if ssid != current_ssid:
                reason = ConnectionResult.CONNECTION_FAILED
                if self.network_service.wifi_dev:
                    state_reason = self.network_service.wifi_dev.get_state_reason()
                    if state_reason == NM.DeviceStateReason.NO_SECRETS:
                        reason = ConnectionResult.INVALID_PASSWORD

                self.mark_failed(ssid, reason, "Connection attempt failed")

    def check_failed_state(self) -> None:
        # mark all pending connections when device enters FAILED state
        for ssid in list(self.pending.keys()):
            reason = ConnectionResult.CONNECTION_FAILED
            if self.network_service.wifi_dev:
                state_reason = self.network_service.wifi_dev.get_state_reason()
                if state_reason == NM.DeviceStateReason.NO_SECRETS:
                    reason = ConnectionResult.INVALID_PASSWORD

            self.mark_failed(ssid, reason, "Connection failed")

    def _check_timeout(self, ssid: str) -> bool:
        if ssid in self.pending:
            logger.warning(f"Connection to {ssid} timed out")
            self.mark_failed(ssid, ConnectionResult.TIMEOUT, "Connection timed out")
        return False

    def _schedule_cleanup(self, ssid: str) -> None:
        logger.info(f"Scheduling cleanup for failed profile: {ssid}")
        GLib.timeout_add(
            NetworkConstants.CLEANUP_DELAY_MS,
            self.network_service._cleanup_connection_profile,
            ssid,
        )


class ConnectionProfileManager:
    def __init__(self, client: Optional[NM.Client]):
        self.client = client

    def find_by_ssid(self, ssid: str) -> Optional[NM.Connection]:
        if not self.client:
            return None

        matches = []

        for conn in self.client.get_connections():
            try:
                wifi = conn.get_setting_wireless()
                if not wifi or not wifi.get_ssid():
                    continue

                conn_ssid = NM.utils_ssid_to_utf8(wifi.get_ssid().get_data())
                if conn_ssid == ssid:
                    matches.append(conn)
            except Exception as e:
                logger.debug(f"Error checking connection: {e}")
                continue

        if not matches:
            return None

        if len(matches) == 1:
            return matches[0]

        # Prioritize enterprise connections (802.1X)
        eap_profiles = [c for c in matches if c.get_setting_802_1x()]
        if eap_profiles:
            return eap_profiles[0]

        # Prioritize WPA-EAP profiles
        def is_wpa_eap(conn):
            sec = conn.get_setting_wireless_security()
            return sec and sec.get_key_mgmt() == "wpa-eap"

        wpa_eap_profiles = [c for c in matches if is_wpa_eap(c)]
        if wpa_eap_profiles:
            return wpa_eap_profiles[0]

        # Return first match
        return matches[0]

    def create(
        self, ssid: str, password: Optional[str]
    ) -> Optional[NM.SimpleConnection]:
        try:
            connection = NM.SimpleConnection.new()

            # Connection settings
            s_con = NM.SettingConnection.new()
            s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
            s_con.set_property(NM.SETTING_CONNECTION_UUID, NM.utils_uuid_generate())
            s_con.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
            connection.add_setting(s_con)

            # Wireless settings
            s_wifi = NM.SettingWireless.new()
            ssid_bytes = GLib.Bytes.new(ssid.encode("utf-8"))
            s_wifi.set_property(NM.SETTING_WIRELESS_SSID, ssid_bytes)
            connection.add_setting(s_wifi)

            # Security settings (if password provided)
            if password:
                s_wifi_sec = NM.SettingWirelessSecurity.new()
                s_wifi_sec.set_property(
                    NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk"
                )
                s_wifi_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
                connection.add_setting(s_wifi_sec)

            return connection
        except Exception as e:
            logger.error(f"Failed to create connection profile: {e}")
            return None

    def update_password(self, connection: NM.Connection, password: str) -> bool:
        try:
            sec = connection.get_setting_wireless_security()
            if not sec:
                logger.warning("Connection has no security settings")
                return False

            sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            connection.commit_changes(True, None)
            logger.debug("Updated password for existing connection")
            return True
        except Exception as e:
            logger.error(f"Failed to update connection password: {e}")
            return False

    def delete(self, ssid: str) -> bool:
        if not self.client:
            logger.error("Cannot delete: no client")
            return False

        try:
            deleted = False
            for conn in self.client.get_connections():
                try:
                    wifi = conn.get_setting_wireless()
                    if not wifi or not wifi.get_ssid():
                        continue

                    conn_ssid = NM.utils_ssid_to_utf8(wifi.get_ssid().get_data())
                    if conn_ssid == ssid:
                        conn.delete_async(None, None, None)
                        logger.info(f"Deleted profile for {ssid}")
                        deleted = True
                except Exception as e:
                    logger.debug(f"Error deleting connection: {e}")
                    continue

            return deleted
        except Exception as e:
            logger.error(f"Failed to delete profiles for {ssid}: {e}")
            return False

    def get_saved_ssids(self) -> List[str]:
        if not self.client:
            return []

        saved_ssids = set()
        try:
            for conn in self.client.get_connections():
                try:
                    wifi = conn.get_setting_wireless()
                    if wifi and wifi.get_ssid():
                        ssid = NM.utils_ssid_to_utf8(wifi.get_ssid().get_data())
                        saved_ssids.add(ssid)
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting saved networks: {e}")

        return sorted(list(saved_ssids))


class ScanManager:
    def __init__(self, wifi_dev: Optional[NM.DeviceWifi], on_complete: Callable):
        self.wifi_dev = wifi_dev
        self.on_complete = on_complete
        self._is_scanning = False
        self._scan_timeout_id: Optional[int] = None

    def update_device(self, wifi_dev: Optional[NM.DeviceWifi]) -> None:
        self.wifi_dev = wifi_dev

    def request_scan(self) -> bool:
        if not self.wifi_dev:
            logger.warning("Cannot scan: no WiFi device")
            return False

        if self._is_scanning:
            logger.debug("Scan already in progress")
            return False

        try:
            self._is_scanning = True
            self.wifi_dev.request_scan_async(None, self._on_scan_complete, None)
            logger.debug("WiFi scan requested")
            return True
        except Exception as e:
            logger.error(f"Scan request failed: {e}")
            self._is_scanning = False
            return False

    def schedule_update(self) -> None:
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)

        self._scan_timeout_id = GLib.timeout_add(
            NetworkConstants.SCAN_DEBOUNCE_MS, self._do_scheduled_update
        )

    def _on_scan_complete(self, device, result, user_data) -> None:
        self._is_scanning = False
        try:
            if device.request_scan_finish(result):
                logger.debug("WiFi scan completed")
                self.on_complete()
            else:
                logger.warning("WiFi scan failed")
        except Exception as e:
            logger.error(f"Scan completion error: {e}")

    def _do_scheduled_update(self) -> bool:
        self._scan_timeout_id = None
        self.request_scan()
        return False


class NetworkService(Service):
    @Signal
    def connection_change(self, ssid: str, connected: bool, status: str = "") -> None:
        """Emitted when connection status changes"""
        ...

    @Signal
    def ap_change(self) -> None:
        """Emitted when available networks list updates"""
        ...

    @Signal
    def connection_result(self, ssid: str, result: object, message: str = "") -> None:
        """Emitted after connection attempt completes"""
        ...

    @Property(bool, default_value=False, flags="readable")
    def wifi_enabled(self) -> bool:
        return self.client.wireless_get_enabled() if self.client else False

    @Property(str, "readable")
    def active_ssid(self) -> str:
        return self._active_ssid

    def __init__(self):
        super().__init__()

        self.client: Optional[NM.Client] = None
        self.wifi_dev: Optional[NM.DeviceWifi] = None

        self._active_ssid: str = ""

        self.ap_manager = AccessPointManager()
        self.connection_state = None
        self.profile_manager = None
        self.scan_manager = None

        self._init_client()

    def _init_client(self) -> None:
        try:
            self.client = NM.Client.new(None)

            if not self.client:
                logger.error("Failed to create NM Client")
                return

            self.connection_state = ConnectionStateMachine(self)
            self.profile_manager = ConnectionProfileManager(self.client)

            self.client.connect("device-added", self._on_device_added)
            self.client.connect("device-removed", self._on_device_removed)

            # find WiFi device
            devices = self.client.get_devices()
            if not devices:
                logger.warning("No network devices found")
                return

            for dev in devices:
                if dev.get_device_type() == NM.DeviceType.WIFI:
                    self._init_wifi_device(dev)
                    break

        except Exception as e:
            logger.error(f"Failed to initialize NetworkManager client: {e}")

    def _init_wifi_device(self, device: NM.DeviceWifi) -> None:
        if not device:
            logger.error("Cannot initialize: device is None")
            return

        try:
            self.wifi_dev = device
            logger.info(f"WiFi device found: {device.get_iface()}")

            self.scan_manager = ScanManager(
                self.wifi_dev, on_complete=self._on_scan_complete
            )

            self.wifi_dev.connect("state-changed", self._on_device_state_change)
            self.wifi_dev.connect(
                "notify::active-access-point", self._on_active_ap_change
            )
            self.wifi_dev.connect("access-point-added", self._on_ap_changed)
            self.wifi_dev.connect("access-point-removed", self._on_ap_changed)

            self.scan()

        except Exception as e:
            logger.error(f"Failed to initialize WiFi device: {e}")
            self.wifi_dev = None

    def init_props(self) -> None:
        if self.wifi_dev:
            self._on_active_ap_change(self.wifi_dev, None)
        else:
            self.connection_change("", False, DeviceStatus.NO_DEVICE.value)

        # init on/off
        self.toggle_wifi_radio(enabled=config.network.wifi.ON)

    def scan(self) -> bool:
        if not self.scan_manager:
            return False
        return self.scan_manager.request_scan()

    def get_wifi_list(self) -> List[dict]:
        if not self.wifi_dev:
            logger.warning("Cannot get WiFi list: no device")
            return []

        active_ap = self.wifi_dev.get_active_access_point()
        active_ssid = self._extract_ssid_from_ap(active_ap)

        networks = self.ap_manager.get_unique_networks(active_ssid)

        return [network.to_dict() for network in networks]

    def get_access_points(self) -> List[NM.AccessPoint]:
        if not self.wifi_dev:
            return []
        return self.wifi_dev.get_access_points()

    def connect_to_network(
        self,
        ssid: str,
        password: Optional[str] = None,
        force_new: bool = False,
    ) -> ConnectionResult:
        """
        Connect to a WiFi network.

        Args:
            ssid: Network SSID
            password: Network password (required for new connections to secured networks)
            force_new: Force creation of new connection profile

        Returns:
            ConnectionResult indicating success or error type
        """
        ssid = ssid.strip()

        if not self.wifi_dev:
            logger.error("Cannot connect: no WiFi device")
            return ConnectionResult.NO_DEVICE

        if not ssid:
            logger.error("Cannot connect: SSID is empty")
            return ConnectionResult.CONNECTION_FAILED

        if self._active_ssid == ssid:
            logger.info(f"Already connected to {ssid}")
            return ConnectionResult.ALREADY_CONNECTED

        ap = self.ap_manager.find_by_ssid(ssid)
        if not ap:
            logger.error(f"Access point not found: {ssid}")
            return ConnectionResult.NETWORK_NOT_FOUND

        try:
            # get profile
            connection = None if force_new else self.profile_manager.find_by_ssid(ssid)

            if connection:
                return self._activate_existing_connection(connection, ssid, password)
            else:
                is_secured = ap.get_wpa_flags() != 0 or ap.get_rsn_flags() != 0
                if is_secured and not password:
                    logger.info(f"Password required for new connection to {ssid}")
                    return ConnectionResult.PASSWORD_REQUIRED

                return self._create_and_activate_connection(ssid, password, ap)

        except Exception as e:
            logger.error(f"Failed to connect to {ssid}: {e}")
            return ConnectionResult.CONNECTION_FAILED

    def disconnect(self) -> bool:
        if not self.wifi_dev:
            logger.error("Cannot disconnect: no WiFi device")
            return False

        try:
            active_conn = self.wifi_dev.get_active_connection()
            if active_conn:
                logger.info("Disconnecting from network")
                self.client.deactivate_connection_async(active_conn, None, None, None)
                return True
            else:
                logger.warning("No active connection to disconnect")
                return False
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False

    def forget_network(self, ssid: str) -> bool:
        return self.profile_manager.delete(ssid)

    def get_saved_networks(self) -> List[str]:
        return self.profile_manager.get_saved_ssids()

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
            
            # CHANGES THE CONFIG!!
            config.network.wifi.ON = new_state

            return True
        except Exception as e:
            logger.error(f"Failed to toggle WiFi: {e}")
            return False

    def _activate_existing_connection(
        self, connection: NM.Connection, ssid: str, password: Optional[str]
    ) -> ConnectionResult:
        logger.info(f"Activating existing connection: {ssid}")

        if password:
            if not self.profile_manager.update_password(connection, password):
                logger.warning("Failed to update password in existing connection")

        try:
            self.client.activate_connection_async(
                connection,
                self.wifi_dev,
                None,
                None,
                self._on_activate_connection_complete,
                ssid,
            )
            return ConnectionResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to activate connection: {e}")
            return ConnectionResult.CONNECTION_FAILED

    # callback for activating existing connection
    def _on_activate_connection_complete(
        self, client: NM.Client, result: Any, ssid: str
    ) -> None:
        try:
            active_conn = client.activate_connection_finish(result)
            if active_conn:
                logger.info(f"Activated connection to {ssid}")
                self.connection_state.track_connection(ssid, active_conn, is_new=False)
            else:
                logger.error(f"Failed to activate connection to {ssid}")
                self.connection_result(
                    ssid, ConnectionResult.CONNECTION_FAILED, "Activation failed"
                )
        except Exception as e:
            logger.error(f"Connection activation error for {ssid}: {e}")
            self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, str(e))

    def _create_and_activate_connection(
        self, ssid: str, password: Optional[str], ap: NM.AccessPoint
    ) -> ConnectionResult:
        logger.info(f"Creating new connection: {ssid}")

        connection = self.profile_manager.create(ssid, password)

        if connection is None or not connection.verify():
            logger.error("Failed to create valid connection profile")
            return ConnectionResult.CONNECTION_FAILED

        try:
            self.client.add_and_activate_connection_async(
                connection,
                self.wifi_dev,
                ap.get_path(),
                None,
                self._on_add_and_activate_complete,
                {"ssid": ssid, "is_new": True},
            )
            return ConnectionResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to add and activate connection: {e}")
            return ConnectionResult.CONNECTION_FAILED

    # callback for adding and activating new connection
    def _on_add_and_activate_complete(
        self, client: NM.Client, result: Any, user_data: dict
    ) -> None:
        ssid = user_data.get("ssid", "Unknown")
        is_new = user_data.get("is_new", False)

        try:
            active_conn = client.add_and_activate_connection_finish(result)

            if not active_conn:
                logger.error(f"Failed to initiate connection to {ssid}")
                if is_new:
                    self.connection_state._schedule_cleanup(ssid)
                self.connection_result(
                    ssid, ConnectionResult.CONNECTION_FAILED, "Connection failed"
                )
                return

            # track connection
            self.connection_state.track_connection(ssid, active_conn, is_new)
            logger.debug(f"Connection initiated for {ssid}, waiting for activation...")

        except GLib.Error as e:
            error_message = str(e)
            logger.error(f"Connection error for {ssid}: {error_message}")

            result_code = self._parse_connection_error(error_message)

            # cleanup failed profile
            if is_new:
                self.connection_state._schedule_cleanup(ssid)

            self.connection_result(ssid, result_code, error_message)

        except Exception as e:
            logger.error(f"Unexpected error connecting to {ssid}: {e}")
            if is_new:
                self.connection_state._schedule_cleanup(ssid)
            self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, str(e))

    def _parse_connection_error(self, error_message: str) -> ConnectionResult:
        error_lower = error_message.lower()

        if "secrets were required" in error_lower or "password" in error_lower:
            return ConnectionResult.INVALID_PASSWORD
        elif "no suitable device" in error_lower:
            return ConnectionResult.NO_DEVICE
        else:
            return ConnectionResult.CONNECTION_FAILED

    def _cleanup_connection_profile(self, ssid: str) -> bool:
        try:
            connection = self.profile_manager.find_by_ssid(ssid)

            if connection:
                logger.info(f"Deleting failed connection profile for {ssid}")
                connection.delete_async(None, None, None)
            else:
                logger.debug(f"No connection profile found to clean up for {ssid}")

        except Exception as e:
            logger.error(f"Error cleaning up connection for {ssid}: {e}")

        return False

    def _on_device_added(self, client: NM.Client, device: NM.Device) -> None:
        if not device:
            return

        if device.get_device_type() == NM.DeviceType.WIFI and not self.wifi_dev:
            logger.info("WiFi device added")
            self._init_wifi_device(device)
            self._update_connection_state()

    def _on_device_removed(self, client: NM.Client, device: NM.Device) -> None:
        if not device or not self.wifi_dev:
            return

        try:
            if device.get_path() == self.wifi_dev.get_path():
                logger.info("WiFi device removed")
                self.wifi_dev = None
                self.ap_manager.update([])
                self._active_ssid = ""
                if self.scan_manager:
                    self.scan_manager.update_device(None)
                self._on_active_ap_change(None, None)

        except Exception as e:
            logger.error(f"Error handling device removed: {e}")

    def _on_device_state_change(
        self, device: NM.DeviceWifi, new_state: int, old_state: int, reason: int
    ) -> None:
        logger.debug(
            f"Device state changed: {old_state} -> {new_state} (reason: {reason})"
        )
        self._update_connection_state(new_state)

    def _on_active_ap_change(self, source: Optional[NM.DeviceWifi], pspec: Any) -> None:
        if source is None:
            self.connection_change("", False, DeviceStatus.NO_DEVICE.value)
            return

        device_state = source.get_state()
        if device_state == NM.DeviceState.UNAVAILABLE:
            self.connection_change("", False, DeviceStatus.WIFI_OFF.value)
            return

        active_ap = source.get_active_access_point()
        if active_ap:
            ssid = self._extract_ssid_from_ap(active_ap)
            if ssid:
                self._active_ssid = ssid
                logger.debug(f"Connected to: {ssid}")
                self.connection_change(ssid, True, DeviceStatus.CONNECTED.value)
            else:
                self.connection_change("", True, "Connected (No SSID)")
        else:
            self.connection_change("", False, DeviceStatus.DISCONNECTED.value)

        self._update_ap_list()

    def _on_ap_changed(self, device: NM.DeviceWifi, ap: NM.AccessPoint) -> None:
        if self.scan_manager:
            self.scan_manager.schedule_update()

    def _on_scan_complete(self) -> None:
        self._update_ap_list()

    def _update_connection_state(self, new_state: Optional[int] = None) -> None:
        if not self.wifi_dev:
            self._emit_state(DeviceStatus.NO_DEVICE, "", False)
            return

        if new_state is None:
            new_state = self.wifi_dev.get_state()

        match new_state:
            case NM.DeviceState.UNAVAILABLE:
                self._emit_state(DeviceStatus.WIFI_OFF, "", False)

            case NM.DeviceState.DISCONNECTED:
                self._emit_state(DeviceStatus.DISCONNECTED, "", False)
                # Only check for failed connections if we're truly disconnected
                # Don't trigger on temporary DISCONNECTED states during connection
                # We'll rely on the timeout mechanism instead

            case (
                NM.DeviceState.PREPARE
                | NM.DeviceState.CONFIG
                | NM.DeviceState.NEED_AUTH
                | NM.DeviceState.IP_CONFIG
                | NM.DeviceState.IP_CHECK
                | NM.DeviceState.SECONDARIES
            ):
                self._emit_state(DeviceStatus.CONNECTING, "", False)

            case NM.DeviceState.ACTIVATED:
                active_ap = self.wifi_dev.get_active_access_point()
                if active_ap:
                    ssid = self._extract_ssid_from_ap(active_ap)
                    if ssid:
                        self._active_ssid = ssid
                        self.connection_state.mark_success(ssid)
                        self._emit_state(DeviceStatus.CONNECTED, ssid, True)
                    else:
                        self._emit_state(DeviceStatus.CONNECTED, "", True)
                else:
                    self._emit_state(DeviceStatus.CONNECTED, "", True)

            case NM.DeviceState.FAILED:
                self._emit_state(DeviceStatus.FAILED, "", False)
                # only mark as failed when we reach the FAILED state
                self.connection_state.check_failed_state()

            case _:
                self._emit_state(DeviceStatus.UNKNOWN, "", False)

    def _emit_state(self, status: DeviceStatus, ssid: str, connected: bool) -> None:
        self._active_ssid = ssid if connected else ""
        self.connection_change(ssid, connected, status.value)

    def _update_ap_list(self, rescan: bool = False) -> None:
        if not self.wifi_dev:
            return

        if rescan:
            self.scan()
            return

        try:
            aps = self.wifi_dev.get_access_points()
            self.ap_manager.update(aps)
            self.ap_change()
        except Exception as e:
            logger.error(f"Error updating AP list: {e}")

    @staticmethod
    def _extract_ssid_from_ap(ap: Optional[NM.AccessPoint]) -> Optional[str]:
        if not ap or not ap.get_ssid():
            return None

        try:
            return NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
        except Exception as e:
            logger.debug(f"Could not extract SSID: {e}")
            return None
