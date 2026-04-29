from loguru import logger
from dataclasses import dataclass
from typing import Optional, Any, Callable

from fabric.core.service import Signal, Property

from .common import (
    DeviceStatus,
    NetworkDevice,
    ConnectionType,
    ConnectionResult,
    NetworkConstants,
)


import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM, GLib
except ValueError:
    logger.error("Failed to load NetworkManager bindings")
    raise


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
        normalized = min(80, 20 * round(strength / 20))
        return cls.ICON_MAP.get(normalized, "network-wireless-no-route-symbolic")


@dataclass
class PendingConnection:
    ssid: str
    active_conn: Any
    is_new: bool
    timestamp: int


class AccessPointManager:
    def __init__(self):
        self.ap_list: list[NM.AccessPoint] = []

    def update(self, new_list: list[NM.AccessPoint]) -> None:
        self.ap_list = new_list

    def get_unique_networks(
        self, active_ssid: Optional[str] = None
    ) -> list[NetworkInfo]:
        # deduplicate by SSID
        ap_dict: dict[str, NM.AccessPoint] = {}

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
    def __init__(self, network_service: "WifiDevice"):
        self.network_service = network_service
        self.pending: dict[str, PendingConnection] = {}

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

    def get_saved_ssids(self) -> list[str]:
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


class WifiDevice(NetworkDevice):
    CONNECTION_TYPE = ConnectionType.WIFI

    @Signal
    def ap_change(self) -> None:
        """Emitted when access points list changes"""
        ...

    @Signal
    def connection_result(
        self, ssid: str, result: object, message: str = ""
    ) -> None: ...

    @Property(str, "readable")
    def active_ssid(self) -> str | None:
        return self._extract_ssid_from_ap(self.get_active_access_point())

    def __init__(self, device: NM.DeviceWifi, client: Optional[NM.Client]):
        super().__init__(device)
        self.client = client

        self.ap_manager = AccessPointManager()
        self.connection_state = ConnectionStateMachine(self)
        self.profile_manager = ConnectionProfileManager(self.client)
        self.scan_manager = ScanManager(device, on_complete=self._on_scan_complete)

        self._sig_ids["state"] = device.connect(
            "state-changed", self._on_device_state_change
        )
        self._sig_ids["active_ap"] = device.connect(
            "notify::active-access-point", self._on_active_ap_change
        )
        self._sig_ids["ap_added"] = device.connect(
            "access-point-added", self._on_ap_changed
        )
        self._sig_ids["ap_removed"] = device.connect(
            "access-point-removed", self._on_ap_changed
        )

        self.scan()
        self._update_connection_state(device.get_state())

    def scan(self) -> bool:
        if not self.scan_manager:
            logger.debug("No Scan Manager available")
            return False
        return self.scan_manager.request_scan()

    def get_networks(self) -> list[dict]:
        if not self.device:
            logger.warning("Cannot get WiFi list: no device")
            return []

        active_ap = self.device.get_active_access_point()
        active_ssid = self._extract_ssid_from_ap(active_ap)

        networks = self.ap_manager.get_unique_networks(active_ssid)
        return [network.to_dict() for network in networks]

    def get_access_points(self) -> list[NM.AccessPoint]:
        if not self.device:
            return []
        return self.device.get_access_points()

    def get_active_access_point(self) -> Optional[NM.AccessPoint]:
        if not self.device:
            return None
        return self.device.get_active_access_point()

    def get_active_connection(self):
        if not self.device:
            return None
        return self.device.get_active_connection()

    def get_state_reason(self) -> Optional[int]:
        if not self.device:
            return None
        try:
            return self.device.get_state_reason()
        except Exception:
            return None

    def get_path(self) -> Optional[str]:
        return self.device.get_path() if self.device else None

    def connect_to_network(
        self,
        ssid: str,
        password: Optional[str] = None,  # required for new connections
        force_new: bool = False,  # force creation of new connection profile
    ) -> ConnectionResult:
        ssid = ssid.strip()

        if not self.device:
            logger.error("Cannot connect: no WiFi device")
            return ConnectionResult.NO_DEVICE

        if not ssid:
            logger.error("Cannot connect: SSID is empty")
            return ConnectionResult.CONNECTION_FAILED

        if self.active_ssid == ssid:
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

    def disconnect_network(self) -> bool:
        if not self.device:
            logger.error("Cannot disconnect: no WiFi device")
            return False

        try:
            active_conn = self.get_active_connection()
            if active_conn:
                logger.info("Disconnecting from network")
                if self.client:
                    self.client.deactivate_connection_async(
                        active_conn, None, None, None
                    )
                return True
            else:
                logger.warning("No active connection to disconnect")
                return False

        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False

    def forget_network(self, ssid: str) -> bool:
        return self.profile_manager.delete(ssid)

    def get_saved_networks(self) -> list[str]:
        return self.profile_manager.get_saved_ssids()

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
                self.device,
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
                self.device,
                ap.get_path(),
                None,
                self._on_add_and_activate_connection_complete,
                {"ssid": ssid, "is_new": True},
            )
            return ConnectionResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to add and activate connection: {e}")
            return ConnectionResult.CONNECTION_FAILED

    # callback for adding and activating new connection
    def _on_add_and_activate_connection_complete(
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

    def _on_device_state_change(
        self, device: NM.DeviceWifi, new_state: int, old_state: int, reason: int
    ) -> None:
        logger.debug(
            f"Device state changed: {old_state} -> {new_state} (reason: {reason})"
        )
        self._update_connection_state(new_state)

    def _on_active_ap_change(self, source: Optional[NM.DeviceWifi], pspec: Any) -> None:
        self._update_ap_list()
        self._update_connection_state()

    def _on_ap_changed(self, device: NM.DeviceWifi, ap: NM.AccessPoint) -> None:
        if self.scan_manager:
            self.scan_manager.schedule_update()

    def _on_scan_complete(self) -> None:
        self._update_ap_list()

    def _get_active_device_state(self) -> int:
        if not self.device:
            return NM.DeviceState.UNKNOWN
        return self.device.get_state()

    def _update_connection_state(self, new_state: Optional[int] = None) -> None:
        dev = self.device
        if not dev:
            self._emit_state(DeviceStatus.NO_DEVICE, "")
            return

        if new_state is None:
            new_state = dev.get_state()

        state = self._map_nm_state(new_state)

        ssid = ""
        active_ap = dev.get_active_access_point()
        if active_ap:
            ssid = self._extract_ssid_from_ap(active_ap) or ""
            if state == DeviceStatus.CONNECTED and ssid:
                self.connection_state.mark_success(ssid)

        if state == DeviceStatus.FAILED:
            self.connection_state.check_failed_state()

        self._emit_state(state, ssid)

    def _emit_state(self, status: DeviceStatus, ssid: str) -> None:
        self._state = status
        self.state_changed(ssid, status)

    def _update_ap_list(self, rescan: bool = False) -> None:
        if not self.device:
            return

        if rescan:
            self.scan()
            return

        try:
            aps = self.get_access_points()
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
