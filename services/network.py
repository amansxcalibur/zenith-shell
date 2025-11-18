import gi
from fabric.core.service import Service, Signal, Property
from loguru import logger

from typing import Optional
from enum import Enum, auto

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except ValueError:
    logger.error("Failed to start network manager")

from gi.repository import GLib


class ConnectionResult(Enum):
    """Result codes for connection attempts"""

    SUCCESS = auto()  # Connection initiated successfully
    PASSWORD_REQUIRED = auto()  # Network is secured, password needed
    NETWORK_NOT_FOUND = auto()  # SSID not in scan results
    NO_DEVICE = auto()  # WiFi device not available
    ALREADY_CONNECTED = auto()  # Already connected to this network
    INVALID_PASSWORD = auto()  # Password validation failed
    CONNECTION_FAILED = auto()  # Generic connection failure
    DEVICE_BUSY = auto()


class NetworkService(Service):

    @Signal
    def connection_change(
        self, ssid: str, connected: bool, status: str = ""
    ) -> None: ...

    @Signal
    def ap_change(self) -> None: ...

    @Signal
    def connection_result(
        self, ssid: str, result: object, message: str = ""
    ) -> None: ...

    @Property(bool, default_value=False, flags="readable")
    def wifi_enabled(self) -> bool:
        self.client.wireless_get_enabled() if self.client else False

    @Property(str, "readable")
    def active_ssid(self) -> str:
        return self._active_ssid

    def __init__(self):
        super().__init__()

        self.client: Optional[NM.Client] = None
        self.wifi_dev: Optional[NM.DeviceWifi] = None
        self.ap_list: list[NM.AccessPoint] = []
        self._active_ssid: str = ""
        self._scan_timeout_id: Optional[int] = None
        self._is_scanning: bool = False
        self._pending_connections: dict = {}

        self._init_client()

    def _init_client(self):
        try:
            self.client = NM.Client.new(None)

            if not self.client:
                logger.error("Failed to create NM.Client")
                return

            self.client.connect("device-added", self._on_device_added)
            self.client.connect("device-removed", self._on_device_removed)

            devices = self.client.get_devices()

            if not devices:
                logger.warning("No network devices found")
                return

            for dev in devices:
                if dev.get_device_type() == NM.DeviceType.WIFI:
                    self._init_wifi_device(device=dev)

            self.scan()
        except Exception as e:
            logger.error(f"Failed to initialize NetworkManager client: {e}")

    def _init_wifi_device(self, device: NM.DeviceWifi):
        if not device:
            logger.error("Cannot initialize: device is None")
            return

        try:
            self.wifi_dev = device
            logger.info(f"WiFi device found: {device.get_iface()}")

            self.wifi_dev.connect("state-changed", self._on_device_state_change)
            self.wifi_dev.connect(
                "notify::active-access-point", self._on_active_ap_change
            )
            self.wifi_dev.connect("access-point-added", self._on_ap_added)
            self.wifi_dev.connect("access-point-removed", self._on_ap_removed)

        except Exception as e:
            logger.error(f"Failed to initilaize WiFi device: {e}")
            self.wifi_dev = None

    def _on_ap_added(self, device, ap):
        self._schedule_scan_update()

    def _on_ap_removed(self, device, ap):
        self._schedule_scan_update()

    def get_wifi_list(self) -> list[dict]:
        if not self.wifi_dev:
            logger.warning("Cannot get WiFi list: no device")
            return []

        active_ap = self.wifi_dev.get_active_access_point()
        active_ssid = None
        
        if active_ap and active_ap.get_ssid():
            try:
                active_ssid = NM.utils_ssid_to_utf8(active_ap.get_ssid().get_data())
            except Exception as e:
                logger.debug(f"Could not get active SSID: {e}")
                active_ssid = None

        def make_ap_dict(ap: NM.AccessPoint) -> dict:
            strength = ap.get_strength()
            ssid = (
                NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
                if ap.get_ssid()
                else "Unknown"
            )
            return {
                "bssid": ap.get_bssid(),
                "ssid": ssid,
                "active": active_ssid is not None and ssid == active_ssid,
                "strength": strength,
                "frequency": ap.get_frequency(),
                "flags": ap.get_flags(),
                "wpa_flags": ap.get_wpa_flags(),
                "rsn_flags": ap.get_rsn_flags(),
                "secured": ap.get_wpa_flags() != 0 or ap.get_rsn_flags() != 0,
                "icon-name": {
                    80: "network-wireless-signal-excellent-symbolic",
                    60: "network-wireless-signal-good-symbolic",
                    40: "network-wireless-signal-ok-symbolic",
                    20: "network-wireless-signal-weak-symbolic",
                    00: "network-wireless-signal-none-symbolic",
                }.get(
                    min(80, 20 * round(ap.get_strength() / 20)),
                    "network-wireless-no-route-symbolic",
                ),
                "last_seen": ap.get_last_seen(),
            }

        # remove duplicates by SSID, keeping strongest signal
        ap_dict = {}
        for ap in self.ap_list:
            try:
                if not ap or not ap.get_ssid():
                    continue
                    
                ssid = NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
                if ssid not in ap_dict or ap.get_strength() > ap_dict[ssid].get_strength():
                    ap_dict[ssid] = ap
            except Exception as e:
                logger.debug(f"Error processing AP: {e}")
                continue

        wifi_list = [make_ap_dict(ap) for ap in ap_dict.values()]
        wifi_list.sort(key=lambda x: x.get("strength", 0), reverse=True)

        return wifi_list

    def get_access_points(self) -> list[NM.AccessPoint]:
        return self.wifi_dev.get_access_points()

    def _schedule_scan_update(self):
        """Debounce AP list updates"""
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
        self._scan_timeout_id = GLib.timeout_add(500, self._update_ap_list, True)

    def _update_ap_list(self, rescan: bool = False):
        if self.wifi_dev:
            if rescan:
                self.scan()
                return False

            aps = self.wifi_dev.get_access_points()
            self.ap_list = aps
            self.ap_change()
        self._scan_timeout_id = None
        return False

    def scan(self):
        if not self.wifi_dev:
            logger.warning("Cannot scan: no WiFi device")
            return False

        if self._is_scanning:
            logger.debug("Scan already in progress")
            return False

        def _on_scan_complete(device, result, user_data):
            self._is_scanning = False
            try:
                if device.request_scan_finish(result):
                    logger.debug("WiFi scan completed")
                    self._update_ap_list()
                else:
                    logger.warning("WiFi scan failed")
            except Exception as e:
                logger.error(f"Scan completion error: {e}")

        try:
            self._is_scanning = True
            self.wifi_dev.request_scan_async(None, _on_scan_complete, None)
            logger.debug("WiFi scan requested")
            return True
        except Exception as e:
            logger.error(f"Scan request failed: {e}")
            return False

    def init_props(self):
        if self.wifi_dev:
            self._on_active_ap_change(self.wifi_dev, None)
        else:
            self.connection_change("", False, "No Device")

    def _on_active_ap_change(self, source, pspec):
        if source is None:
            self.connection_change("", False, "No Device")
            return

        device_state = source.get_state()
        if device_state == NM.DeviceState.UNAVAILABLE:
            self.connection_change("", False, "Wi-Fi Off")
            return

        active_ap = source.get_active_access_point()
        if active_ap:
            ssid = active_ap.get_ssid().get_data().decode("utf-8")
            self._active_ssid = ssid
            logger.debug(f"Connected to: {ssid}")
            self.connection_change(ssid, True, "Connected")
        else:
            self.connection_change("", False, "Wi-Fi On (No Connection)")

        self._update_ap_list()

    def _on_device_state_change(self, device, new_state, old_state, reason):
        logger.debug(f"Device state changed: {old_state} -> {new_state}")
        self._update_connection_state(new_state)

    def _update_connection_state(self, new_state=None):
        if not self.wifi_dev:
            self._active_ssid = ""
            self.connection_change("", False, "No Device")
            return

        if new_state is None:
            new_state = self.wifi_dev.get_state()

        match new_state:
            case NM.DeviceState.UNAVAILABLE:
                self._active_ssid = ""
                self.connection_change("", False, "Wi-Fi Off")

            case NM.DeviceState.DISCONNECTED:
                self._active_ssid = ""
                self.connection_change("", False, "Wi-Fi On (No Connection)")

                self._check_pending_connections_failed()

            case (
                NM.DeviceState.PREPARE
                | NM.DeviceState.CONFIG
                | NM.DeviceState.NEED_AUTH
                | NM.DeviceState.IP_CONFIG
                | NM.DeviceState.IP_CHECK
                | NM.DeviceState.SECONDARIES
            ):
                self.connection_change("", False, "Connecting…")

            case NM.DeviceState.ACTIVATED:
                active_ap = self.wifi_dev.get_active_access_point()
                if active_ap:
                    ssid = active_ap.get_ssid().get_data().decode("utf-8")
                    self._active_ssid = ssid
                    self.connection_change(ssid, True, "Connected")
                else:
                    self._active_ssid = ""
                    self.connection_change("", True, "Connected (No SSID)")

            case NM.DeviceState.FAILED:
                self._active_ssid = ""
                self.connection_change("", False, "Connection Failed")

            case _:
                self.connection_change("", False, "Unknown")

    def _check_pending_connections_failed(self):
        """Check if any pending connections have failed and clean them up"""
        if not self._pending_connections:
            return
        
        # Get current connection attempt SSID if any
        current_ssid = None
        if self.wifi_dev:
            active_conn = self.wifi_dev.get_active_connection()
            if active_conn:
                conn = active_conn.get_connection()
                if conn:
                    wifi_setting = conn.get_setting_wireless()
                    if wifi_setting and wifi_setting.get_ssid():
                        current_ssid = NM.utils_ssid_to_utf8(wifi_setting.get_ssid().get_data())
        
        # Clean up all pending connections except the current one
        for ssid in list(self._pending_connections.keys()):
            if ssid != current_ssid:
                pending = self._pending_connections.pop(ssid)
                logger.warning(f"Pending connection to {ssid} failed")
                
                if pending.get("is_new"):
                    logger.info(f"Cleaning up failed connection profile for {ssid}")
                    self._cleanup_failed_connection(ssid)
                
                # Determine if it was a password issue
                # If device went from NEED_AUTH to DISCONNECTED, likely bad password
                if self.wifi_dev and self.wifi_dev.get_state_reason() == NM.DeviceStateReason.NO_SECRETS:
                    self.connection_result(ssid, ConnectionResult.INVALID_PASSWORD, "Invalid password")
                else:
                    self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, "Connection failed")

    def _on_device_added(self, client, device):
        if not device:
            return

        if device.get_device_type() == NM.DeviceType.WIFI and not self.wifi_dev:
            logger.info("WiFi device added")
            self._init_wifi_device(device)
            self._update_connection_state()

    def _on_device_removed(self, client, device):
        if not device or not self.wifi_dev:
            return

        try:
            if device.get_path() == self.wifi_dev.get_path():
                logger.info("WiFi device removed")
                self.wifi_dev = None
                self.ap_list = []
                self._active_ssid = ""
                self._on_active_ap_change(None, None)

        except Exception as e:
            logger.error(f"Error handling device removed: {e}")

    # def do_toggle_wifi_connection(self):
    #     if self.wifi_dev.get_active_connection():
    #         self.wifi_dev.disconnect()
    #     else:
    #         self.wifi_dev.reapply_connection()

    def toggle_wifi_radio(self, enabled: Optional[bool] = None) -> bool:
        """
        Enable or disable WiFi radio

        Args:
            enabled: True to enable, False to disable, None to toggle
        """
        if not self.client:
            logger.error("Cannot toggle WiFi: no client")
            return False

        try:
            current = self.client.wireless_get_enabled()
            new_state = not current if enabled is None else enabled

            logger.info(f"Setting WiFi: {new_state}")
            self.client.wireless_set_enabled(new_state)
            return True
        except Exception as e:
            logger.error(f"Failed to toggle WiFi: {e}")
            return False

    def connect_to_network(
        self,
        ssid: str,
        password: Optional[str] = None,
        force_new: bool = False,
    ) -> ConnectionResult:
        if not self.wifi_dev:
            logger.error("Cannot connect: no WiFi device")
            return ConnectionResult.NO_DEVICE

        if not ssid:
            logger.error("Cannot connect: SSID is empty")
            return ConnectionResult.CONNECTION_FAILED

        ssid = ssid.strip()

        if self._active_ssid == ssid:
            logger.info(f"Already connected to {ssid}")
            return ConnectionResult.ALREADY_CONNECTED

        try:
            ap = self._find_ap_by_ssid(ssid)
            if not ap:
                logger.error(f"Access point not found: {ssid}")
                return ConnectionResult.NETWORK_NOT_FOUND

            connection = None if force_new else self._find_connection_by_ssid(ssid)

            if connection:
                # activate existing connection
                logger.info(f"Activating existing connection: {ssid}")

                if password:
                    # Update password in existing connection
                    if not self._update_connection_password(connection, password):
                        logger.warning(
                            "Failed to update password in existing connection"
                        )

                self.client.activate_connection_async(
                    connection, self.wifi_dev, None, None, None, None
                )
                return ConnectionResult.SUCCESS
            else:
                # create new connection
                if self._is_secured(ap) and not password:
                    logger.info(f"Password required for {ssid}")
                    return ConnectionResult.PASSWORD_REQUIRED

                logger.info(f"Creating new connection: {ssid}")
                connection = self._create_connection(ssid, password)

                if connection is None or not connection.verify():
                    logger.error("Failed to create connection profile")
                    return ConnectionResult.CONNECTION_FAILED

                self.client.add_and_activate_connection_async(
                    connection,
                    self.wifi_dev,
                    ap.get_path(),
                    None,
                    self._on_add_and_activate_connection,
                    {"ssid": ssid, "is_new": True},
                )

                return ConnectionResult.SUCCESS

        except Exception as e:
            logger.error(f"Failed to connect to {ssid}: {e}")
            return ConnectionResult.CONNECTION_FAILED
        
    def _on_activate_connection(self, client, result, ssid):
        """Callback for activating existing connection"""
        try:
            active_conn = client.activate_connection_finish(result)
            if active_conn:
                logger.info(f"Successfully activated connection to {ssid}")
            else:
                logger.error(f"Failed to activate connection to {ssid}")
                self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, "Activation failed")
        except Exception as e:
            logger.error(f"Connection activation error for {ssid}: {e}")
            self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, str(e))

    def _on_add_and_activate_connection(self, client, result, user_data):
        """Callback for adding and activating new connection"""
        ssid = user_data.get("ssid", "Unknown")
        is_new = user_data.get("is_new", False)
        
        try:
            active_conn = client.add_and_activate_connection_finish(result)
            
            if not active_conn:
                logger.error(f"Failed to initiate connection to {ssid}")
                if is_new:
                    self._cleanup_failed_connection(ssid)
                self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, "Connection failed")
                return
            
            # Connection initiated successfully, but not yet validated
            # Store it for potential cleanup if it fails during activation
            if is_new:
                self._pending_connections[ssid] = {
                    "active_conn": active_conn,
                    "is_new": True,
                    "timestamp": GLib.get_monotonic_time()
                }
                
                # Set a timeout to clean up if connection doesn't complete in 30 seconds
                GLib.timeout_add_seconds(30, self._check_connection_timeout, ssid)
            
            logger.debug(f"Connection initiated for {ssid}, waiting for activation...")
            # Don't emit SUCCESS yet - wait for device state to become ACTIVATED
                
        except GLib.Error as e:
            error_message = str(e)
            logger.error(f"Connection error for {ssid}: {error_message}")
            
            # Determine the type of error
            result_code = ConnectionResult.CONNECTION_FAILED
            
            if "secrets were required" in error_message.lower() or "password" in error_message.lower():
                result_code = ConnectionResult.INVALID_PASSWORD
                logger.info(f"Invalid password for {ssid}")
            elif "no suitable device" in error_message.lower():
                result_code = ConnectionResult.NO_DEVICE
            
            # Clean up the failed connection profile if it was newly created
            if is_new:
                logger.info(f"Cleaning up failed connection profile for {ssid} after error")
                self._cleanup_failed_connection(ssid)
            
            self.connection_result(ssid, result_code, error_message)
            
        except Exception as e:
            logger.error(f"Unexpected error connecting to {ssid}: {e}")
            
            if is_new:
                self._cleanup_failed_connection(ssid)
            
            self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, str(e))

    def _cleanup_failed_connection(self, ssid: str):
        try:
            # Use a small delay to ensure the connection is fully processed
            GLib.timeout_add(500, self._do_cleanup_connection, ssid)
        except Exception as e:
            logger.error(f"Failed to schedule cleanup for {ssid}: {e}")

    def _do_cleanup_connection(self, ssid: str) -> bool:
        try:
            connection = self._find_connection_by_ssid(ssid)
            
            if connection:
                logger.info(f"Deleting failed connection profile for {ssid}")
                connection.delete_async(None, None, None)
            else:
                logger.debug(f"No connection profile found to clean up for {ssid}")
                
        except Exception as e:
            logger.error(f"Error cleaning up connection for {ssid}: {e}")
        
        return False 

    def _update_connection_password(
        self, connection: NM.Connection, password: str
    ) -> bool:
        try:
            # get wireless security settings
            sec = connection.get_setting_wireless_security()
            if not sec:
                return False

            sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)

            connection.commit_changes(True, None)
            logger.debug("Updated password for existing connection")
            return True

        except Exception as e:
            logger.error(f"Failed to update connection password: {e}")
            return False

    def _is_secured(self, ap: NM.AccessPoint) -> bool:
        """Check if AP requires password"""
        return ap.get_wpa_flags() != 0 or ap.get_rsn_flags() != 0

    def _find_ap_by_ssid(self, ssid: str) -> Optional[NM.AccessPoint]:
        for ap in self.ap_list:
            if not ap:
                continue
            if ap.get_ssid():
                ap_ssid = NM.utils_ssid_to_utf8(ap.get_ssid().get_data())
                if ap_ssid == ssid:
                    return ap
        return None

    def _find_connection_by_ssid(self, ssid: str) -> Optional[NM.Connection]:
        if not self.client:
            return None

        matches = []

        for conn in self.client.get_connections():
            wifi = conn.get_setting_wireless()
            if not wifi or not wifi.get_ssid():
                continue

            conn_ssid = NM.utils_ssid_to_utf8(wifi.get_ssid().get_data())
            if conn_ssid != ssid:
                continue

            matches.append(conn)

        if not matches:
            return None

        if len(matches) == 1:
            return matches[0]

        # 1. Prefer enterprise connections (802.1X)
        eap_profiles = [c for c in matches if c.get_setting_802_1x()]
        if eap_profiles:
            return eap_profiles[0]

        # 2. Prefer WPA-EAP profiles
        def is_wpa_eap(c):
            sec = c.get_setting_wireless_security()
            return sec and sec.get_key_mgmt() == "wpa-eap"

        wpa_eap_profiles = [c for c in matches if is_wpa_eap(c)]
        if wpa_eap_profiles:
            return wpa_eap_profiles[0]

        # 3. Otherwise return the best candidate
        return matches[0]

    def _create_connection(
        self, ssid: str, password: Optional[str]
    ) -> Optional[NM.SimpleConnection]:
        """Create a minimal connection profile - NM will complete it using the AP"""

        connection = NM.SimpleConnection.new()

        # Settings Config
        # Connection
        s_con = NM.SettingConnection.new()
        s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
        s_con.set_property(NM.SETTING_CONNECTION_UUID, NM.utils_uuid_generate())
        s_con.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
        connection.add_setting(s_con)

        # Wireless
        s_wifi = NM.SettingWireless.new()
        ssid_bytes = GLib.Bytes.new(ssid.encode("utf-8"))
        s_wifi.set_property(NM.SETTING_WIRELESS_SSID, ssid_bytes)
        connection.add_setting(s_wifi)

        # Password
        if password:
            s_wifi_sec = NM.SettingWirelessSecurity.new()
            s_wifi_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk")
            s_wifi_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            connection.add_setting(s_wifi_sec)

        # NetworkManager will auto-configure:
        # - IP settings (IPv4/IPv6)
        # - Mode, band, channel (from AP)
        # - Security details (from AP capabilities)

        return connection

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

    def get_saved_networks(self) -> list[str]:
        if not self.client:
            return []

        saved_ssids = set()
        try:
            for conn in self.client.get_connections():
                if not conn:
                    continue

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

    def forget_network(self, ssid: str) -> bool:
        if not self.client:
            logger.error("Cannot forget network: no client")
            return False

        try:
            # Find all connections for this SSID
            connections_to_delete = []
            for conn in self.client.get_connections():
                if not conn:
                    continue

                try:
                    wifi = conn.get_setting_wireless()
                    if not wifi or not wifi.get_ssid():
                        continue

                    conn_ssid = NM.utils_ssid_to_utf8(wifi.get_ssid().get_data())
                    if conn_ssid == ssid:
                        connections_to_delete.append(conn)
                except Exception as e:
                    logger.debug(f"Error checking connection: {e}")
                    continue

            if not connections_to_delete:
                logger.warning(f"No saved profiles found for {ssid}")
                return False

            # Delete all matching connections
            for conn in connections_to_delete:
                try:
                    conn.delete_async(None, None, None)
                    logger.info(f"Deleted profile for {ssid}")
                except Exception as e:
                    logger.error(f"Failed to delete profile: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to forget network {ssid}: {e}")
            return False

    def _on_connection_result(
        self, source, ssid: str, result: ConnectionResult, message: str
    ):

        if result == ConnectionResult.INVALID_PASSWORD:
            # Show password dialog again with error message
            self._show_password_dialog(
                ssid, error_message="Incorrect password. Please try again."
            )

        elif result == ConnectionResult.CONNECTION_FAILED:
            self._show_notification(f"Failed to connect to '{ssid}': {message}")

        elif result == ConnectionResult.SUCCESS:
            logger.info(f"Successfully connected to {ssid}")
            self._show_notification(f"Connected to {ssid}")

            # Close password dialog if open
            if self._password_dialog:
                self._password_dialog.destroy()
                self._password_dialog = None

        elif result == ConnectionResult.NO_DEVICE:
            self._show_notification("No WiFi device available")

        elif result == ConnectionResult.NETWORK_NOT_FOUND:
            self._show_notification(f"Network '{ssid}' not found")

    def _check_connection_timeout(self, ssid: str) -> bool:
        if ssid in self._pending_connections:
            logger.warning(f"Connection to {ssid} timed out")
            pending = self._pending_connections.pop(ssid)
            if pending.get("is_new"):
                self._cleanup_failed_connection(ssid)
            self.connection_result(ssid, ConnectionResult.CONNECTION_FAILED, "Connection timed out")
        return False  # Don't repeat
