# Network Service - Complete Workflows

## Workflow 1: Service Initialization

```
1. NetworkService.__init__()
   ├─ Create managers (uninitialized)
   │  ├─ ap_manager = AccessPointManager()
   │  ├─ connection_state = None (pending client)
   │  ├─ profile_manager = None (pending client)
   │  └─ scan_manager = None (pending device)
   └─ Call _init_client()

2. _init_client()
   ├─ Create NM.Client
   ├─ Initialize managers with client
   │  ├─ connection_state = ConnectionStateMachine(self)
   │  └─ profile_manager = ConnectionProfileManager(client)
   ├─ Connect client signals
   │  ├─ "device-added" → _on_device_added()
   │  └─ "device-removed" → _on_device_removed()
   ├─ Get all devices
   └─ Find WiFi device → Call _init_wifi_device(device)

3. _init_wifi_device(device)
   ├─ Store wifi_dev reference
   ├─ Initialize scan_manager
   │  └─ scan_manager = ScanManager(wifi_dev, on_complete=_on_scan_complete)
   ├─ Connect device signals
   │  ├─ "state-changed" → _on_device_state_change()
   │  ├─ "notify::active-access-point" → _on_active_ap_change()
   │  ├─ "access-point-added" → _on_ap_changed()
   │  └─ "access-point-removed" → _on_ap_changed()
   └─ Call scan() for initial network list

4. scan()
   └─ scan_manager.request_scan()
      ├─ wifi_dev.request_scan_async(callback=_on_scan_complete)
      └─ Set _is_scanning = True

5. _on_scan_complete()
   ├─ Set _is_scanning = False
   └─ Call _update_ap_list()

6. _update_ap_list()
   ├─ Get access points from wifi_dev
   ├─ ap_manager.update(aps)
   └─ Emit ap_change signal → UI updates
```

---

## Workflow 2: Connect to Network (Saved Profile Exists)

```
1. connect_to_network(ssid, password=None)
   ├─ Validate device exists → NO_DEVICE
   ├─ Validate SSID not empty → CONNECTION_FAILED
   ├─ Check if already connected → ALREADY_CONNECTED
   ├─ ap_manager.find_by_ssid(ssid) → Find access point
   │  └─ Not found → NETWORK_NOT_FOUND
   └─ profile_manager.find_by_ssid(ssid)
      └─ Found → Go to step 2

2. _activate_existing_connection(connection, ssid, password)
   ├─ If password provided
   │  └─ profile_manager.update_password(connection, password)
   └─ client.activate_connection_async()
      ├─ Pass connection, device, callback
      └─ Callback: _on_activate_connection_complete()

3. _on_activate_connection_complete(result, ssid)
   ├─ active_conn = client.activate_connection_finish(result)
   ├─ If success
   │  └─ connection_state.track_connection(ssid, active_conn, is_new=False)
   └─ If failed
      └─ Emit connection_result(ssid, CONNECTION_FAILED)

4. connection_state.track_connection(ssid, active_conn, is_new=False)
   ├─ Create PendingConnection object
   │  ├─ ssid
   │  ├─ active_conn
   │  ├─ is_new = False
   │  └─ timestamp
   ├─ Store in pending dict: pending[ssid] = PendingConnection
   └─ GLib.timeout_add_seconds(30, _check_timeout, ssid)

5. Device state changes (automatic, triggered by NetworkManager)
   └─ _on_device_state_change(new_state) → Multiple rapid transitions
      ├─ PREPARE (30) → Emit "Connecting..."
      ├─ CONFIG (40) → Emit "Connecting..."
      ├─ IP_CONFIG (70) → Emit "Connecting..."
      ├─ IP_CHECK (80) → Emit "Connecting..."
      ├─ SECONDARIES (90) → Emit "Connecting..."
      └─ ACTIVATED (100) → Go to step 6

6. _update_connection_state(new_state=ACTIVATED)
   ├─ Get active access point
   ├─ Extract SSID
   ├─ Set _active_ssid = ssid
   ├─ connection_state.mark_success(ssid)
   │  ├─ Remove from pending dict: del pending[ssid]
   │  └─ Emit connection_result(ssid, SUCCESS)
   └─ _emit_state(CONNECTED, ssid, True)
      └─ Emit connection_change(ssid, True, "Connected") → UI updates

7. TIMEOUT PATH (if connection doesn't complete)
   └─ After 30 seconds: _check_timeout(ssid)
      └─ If still in pending dict
         └─ connection_state.mark_failed(ssid, TIMEOUT)
            ├─ Remove from pending dict
            ├─ If is_new=True → Schedule cleanup (N/A for existing profile)
            └─ Emit connection_result(ssid, TIMEOUT)

8. FAILURE PATH (if device reaches FAILED state)
   └─ _on_device_state_change(new_state=FAILED)
      └─ connection_state.check_failed_state()
         └─ For each ssid in pending
            └─ mark_failed(ssid, CONNECTION_FAILED or INVALID_PASSWORD)
```

---

## Workflow 3: Connect to Network (No Saved Profile - New Connection)

```
1. connect_to_network(ssid, password)
   ├─ Validate device, SSID, not already connected
   ├─ ap_manager.find_by_ssid(ssid) → Find access point
   └─ profile_manager.find_by_ssid(ssid)
      └─ Not found → Check security
         ├─ is_secured = (ap.get_wpa_flags() != 0 or ap.get_rsn_flags() != 0)
         ├─ If secured AND no password → Return PASSWORD_REQUIRED
         └─ Go to step 2

2. _create_and_activate_connection(ssid, password, ap)
   ├─ profile_manager.create(ssid, password)
   │  ├─ Create NM.SimpleConnection()
   │  ├─ Add connection settings (ID, UUID, type)
   │  ├─ Add wireless settings (SSID)
   │  ├─ If password → Add security settings (WPA-PSK)
   │  └─ Return connection profile
   ├─ Verify connection profile
   └─ client.add_and_activate_connection_async()
      ├─ Pass connection, device, ap_path, callback
      ├─ user_data = {"ssid": ssid, "is_new": True}
      └─ Callback: _on_add_and_activate_complete()

3. _on_add_and_activate_complete(result, user_data)
   ├─ Extract ssid and is_new from user_data
   ├─ active_conn = client.add_and_activate_connection_finish(result)
   ├─ If active_conn is None
   │  ├─ If is_new → Schedule cleanup
   │  └─ Emit connection_result(ssid, CONNECTION_FAILED)
   ├─ If GLib.Error (e.g., wrong password)
   │  ├─ Parse error → Determine result code
   │  │  ├─ "secrets" or "password" → INVALID_PASSWORD
   │  │  ├─ "no suitable device" → NO_DEVICE
   │  │  └─ Otherwise → CONNECTION_FAILED
   │  ├─ If is_new → Schedule cleanup
   │  └─ Emit connection_result(ssid, result_code, error_message)
   └─ If success → Go to step 4

4. connection_state.track_connection(ssid, active_conn, is_new=True)
   ├─ Create PendingConnection object
   │  ├─ ssid
   │  ├─ active_conn
   │  ├─ is_new = True (important for cleanup)
   │  └─ timestamp
   ├─ Store in pending dict
   └─ GLib.timeout_add_seconds(30, _check_timeout, ssid)

5. Device state changes (same as Workflow 2)
   └─ Multiple state transitions → Eventually reaches ACTIVATED or FAILED

6A. SUCCESS PATH: Device reaches ACTIVATED
   └─ _update_connection_state(new_state=ACTIVATED)
      └─ connection_state.mark_success(ssid)
         ├─ Remove from pending dict
         ├─ Emit connection_result(ssid, SUCCESS) → UI closes password dialog
         └─ Profile is saved permanently in NetworkManager

6B. FAILURE PATH: Device reaches FAILED
   └─ _update_connection_state(new_state=FAILED)
      └─ connection_state.check_failed_state()
         └─ connection_state.mark_failed(ssid, INVALID_PASSWORD or CONNECTION_FAILED)
            ├─ If is_new=True → _schedule_cleanup(ssid)
            │  └─ GLib.timeout_add(500ms, _cleanup_connection_profile, ssid)
            └─ Emit connection_result(ssid, INVALID_PASSWORD)
               └─ UI shows password dialog again with error

7. _cleanup_connection_profile(ssid) [Only for failed new connections]
   ├─ Find connection profile by SSID
   ├─ If found
   │  └─ connection.delete_async() → Remove failed profile from NetworkManager
   └─ Return False (don't repeat timeout)

8. TIMEOUT PATH (if connection doesn't complete in 30s)
   └─ _check_timeout(ssid)
      └─ If still in pending dict
         └─ mark_failed(ssid, TIMEOUT)
            ├─ If is_new=True → Schedule cleanup
            └─ Emit connection_result(ssid, TIMEOUT)
```

---

## Workflow 4: User Clicks Network in UI (Widget Side)

```
1. User clicks WifiButton in UI
   └─ WifiButton._on_clicked()
      └─ Call on_connect callback → Network._handle_network_connect(ssid)

2. Network._handle_network_connect(ssid, password=None)
   └─ result = nm.connect_to_network(ssid, password)

3. Handle ConnectionResult
   ├─ PASSWORD_REQUIRED
   │  └─ _show_password_dialog(ssid)
   │     └─ PasswordDialog.show(ssid, on_submit=callback)
   │        └─ User enters password → Callback calls _handle_network_connect(ssid, password)
   │           └─ Goes back to step 2 with password
   │
   ├─ ALREADY_CONNECTED
   │  └─ Log info (already connected)
   │
   ├─ NETWORK_NOT_FOUND
   │  └─ Show notification "Network not found"
   │
   ├─ NO_DEVICE
   │  └─ Show notification "No WiFi device"
   │
   ├─ CONNECTION_FAILED
   │  └─ Show notification "Failed to connect"
   │
   └─ SUCCESS
      └─ Show notification "Connecting..." (actual result comes via signal)

4. Wait for signal: connection_result
   └─ Network._on_connection_result(ssid, result, message)
      ├─ INVALID_PASSWORD
      │  └─ _show_password_dialog(ssid, error_message="Incorrect password")
      │     └─ User can retry with new password
      │
      ├─ SUCCESS
      │  ├─ Show notification "Connected to {ssid}"
      │  └─ Close password dialog if open
      │
      └─ Other failures
         └─ Show appropriate notification

5. Wait for signal: connection_change
   └─ Network._on_connection_change(ssid, connected, status)
      ├─ Update tile visual state (on/off style class)
      ├─ Update label text
      │  ├─ If connected → Show SSID
      │  └─ If not connected → Show status ("Off", "Disconnected", etc.)
      └─ Update WiFi toggle state

6. Wait for signal: ap_change
   └─ Network._on_ap_change()
      └─ wifi_list = nm.get_wifi_list()
         └─ NetworkListManager.update(wifi_list)
            ├─ Clear existing lists
            ├─ Create WifiButton for each network
            ├─ Separate into active vs available
            └─ Populate containers → UI updates
```

---

## Workflow 5: Disconnect from Network

```
1. User right-clicks network → "Disconnect"
   └─ WifiButton._disconnect_network()
      └─ nm.disconnect()

2. disconnect()
   ├─ Validate wifi_dev exists
   ├─ Get active connection
   │  └─ Not found → Return False
   └─ client.deactivate_connection_async(active_conn)

3. Device state changes
   └─ _on_device_state_change(new_state=DISCONNECTED)
      └─ _update_connection_state(DISCONNECTED)
         ├─ Set _active_ssid = ""
         └─ Emit connection_change("", False, "Wi-Fi On (No Connection)")
            └─ UI updates to show disconnected state
```

---

## Workflow 6: Forget Network

```
1. User right-clicks saved network → "Forget Network"
   └─ WifiButton._forget_network()
      ├─ Show confirmation dialog
      └─ If confirmed → nm.forget_network(ssid)

2. forget_network(ssid)
   └─ profile_manager.delete(ssid)
      ├─ Get all connections from client
      ├─ For each connection
      │  ├─ Check if SSID matches
      │  └─ If match → connection.delete_async()
      └─ Return success/failure

3. UI updates automatically
   └─ Next scan/AP list update
      └─ WifiButton rebuilds without "saved" indicator
```

---

## Workflow 7: Update Saved Password

```
1. User clicks settings icon on saved network
   └─ WifiButton._show_update_password_dialog()
      └─ PasswordDialog.show_update(ssid, on_update=callback)

2. User enters new password → Click "Save"
   └─ Callback: WifiButton._update_saved_password(new_password)
      └─ nm.profile_manager.find_by_ssid(ssid)
         └─ nm.profile_manager.update_password(connection, new_password)
            ├─ Get security settings from connection
            ├─ Set new PSK (password)
            ├─ connection.commit_changes() → Save to NetworkManager
            └─ Return success/failure

3. Show notification
   ├─ Success → "Password for {ssid} has been updated"
   └─ Failure → "Could not update password for {ssid}"
```

---

## Workflow 8: WiFi Radio Toggle

```
1. User toggles WiFi switch in UI
   └─ Network._on_toggle_wifi(switch, enabled)
      └─ nm.toggle_wifi_radio(enabled)

2. toggle_wifi_radio(enabled)
   ├─ Get current state from client
   ├─ Determine new state (toggle if None, else use provided)
   └─ client.wireless_set_enabled(new_state)

3. Device state changes
   ├─ If disabled → UNAVAILABLE
   │  └─ Emit connection_change("", False, "Wi-Fi Off")
   │     └─ UI updates: switch off, tile shows "Off"
   │
   └─ If enabled → DISCONNECTED
      └─ Emit connection_change("", False, "Wi-Fi On (No Connection)")
         └─ UI updates: switch on, tile shows "Disconnected"

4. Scan triggers automatically when enabled
   └─ AP list updates → UI shows available networks
```

---

## Workflow 9: Scan for Networks

```
1. User clicks refresh button OR automatic trigger
   └─ scan_manager.request_scan()

2. request_scan()
   ├─ Check if scan already in progress → Skip
   ├─ Set _is_scanning = True
   └─ wifi_dev.request_scan_async(callback=_on_scan_complete)

3. _on_scan_complete() [After ~1-2 seconds]
   ├─ Set _is_scanning = False
   └─ Call _update_ap_list()

4. _update_ap_list()
   ├─ Get access points from wifi_dev.get_access_points()
   ├─ ap_manager.update(aps)
   └─ Emit ap_change signal

5. UI receives ap_change signal
   └─ Network._on_ap_change()
      └─ wifi_list = nm.get_wifi_list()
         ├─ ap_manager.get_unique_networks()
         │  ├─ Deduplicate by SSID (keep strongest)
         │  ├─ Convert to NetworkInfo objects
         │  └─ Sort by signal strength
         └─ NetworkListManager.update(wifi_list)
            └─ Rebuild network list in UI
```

---

## Workflow 10: Access Point Added/Removed (Automatic)

```
1. NetworkManager detects AP change
   └─ Emits "access-point-added" or "access-point-removed" signal
      └─ _on_ap_changed(device, ap)

2. _on_ap_changed()
   └─ scan_manager.schedule_update()
      ├─ Cancel any existing scheduled scan
      └─ GLib.timeout_add(500ms, _do_scheduled_update)
         └─ Debouncing: Multiple rapid AP changes → Single scan after 500ms

3. _do_scheduled_update()
   └─ scan_manager.request_scan()
      └─ Goes to Workflow 9, step 2
```

---

## Key Concepts Summary

### Pending Connection Tracking
- **Purpose**: Track connections in progress to handle success/failure
- **is_new flag**: Determines if profile should be cleaned up on failure
  - `True`: New connection, delete profile if it fails
  - `False`: Existing saved connection, keep profile even if connection fails

### State Transitions (NetworkManager Device States)
```
Connection Process:
30 (DISCONNECTED) → 40 (PREPARE) → 50 (CONFIG) → 60 (NEED_AUTH)
→ 70 (IP_CONFIG) → 80 (IP_CHECK) → 90 (SECONDARIES) → 100 (ACTIVATED)

Note: Device may briefly return to DISCONNECTED during connection.
This is normal and should NOT trigger failure detection.
```

### Cleanup Logic
- Only triggered for **new** connection profiles that fail
- Delayed by 500ms to ensure connection is fully processed
- Prevents orphaned failed profiles in NetworkManager

### Signal Flow
```
NetworkService                    UI (Network widget)
     │                                   │
     ├── connection_change ──────────────→ Update visual state & labels
     ├── ap_change ───────────────────────→ Rebuild network list
     └── connection_result ───────────────→ Handle success/failure, show dialogs
```