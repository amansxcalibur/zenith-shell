from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric.utils.helpers import exec_shell_command_async

from modules.tile import Tile
from widgets.clipping_box import ClippingBox
from utils.cursor import add_hover_cursor
from services.network import NetworkService, ConnectionResult

import icons

from loguru import logger
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


class Network(Tile):
    WINDOW_MAX_WIDTH = 250
    WINDOW_MAX_HEIGHT = 250
    MAX_SSID_DISPLAY_LENGTH = 8

    def __init__(self, **kwargs):
        self.state = None
        self._is_initialized = False
        self._password_dialog = None

        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
            ellipsization="end",
            max_chars_width=self.MAX_SSID_DISPLAY_LENGTH,
        )

        self.nm = NetworkService()
        self.nm.connect("connection-change", self._on_connection_change)
        self.nm.connect("ap-change", self.on_ap_change)
        self.nm.connect("connection-result", self._on_connection_result)

        self.wifi_toggle = Gtk.Switch(name="matugen-switcher")
        self.wifi_toggle.connect("notify::active", self._do_toggle_wifi)
        self.wifi_toggle.set_active(True)
        self.wifi_toggle.set_visible(True)

        self.active_connection = ClippingBox(
            name="network-scrolled-window-container",
            orientation="v",
            children=[],
        )
        self.connection_container = Box(
            name="connection-container",
            orientation="v",
            spacing=2,
            children=[],
        )
        self.scrolled_container = ClippingBox(
            name="network-scrolled-window-container",
            children=ScrolledWindow(
                name="network-scrolled-window",
                h_expand=True,
                max_content_size=(
                    self.WINDOW_MAX_WIDTH,
                    self.WINDOW_MAX_HEIGHT,
                ),
                h_scrollbar_policy="external",
                v_scrollbar_policy="external",
                child=self.connection_container,
            ),
        )
        self.menu = Box(
            name="network-menu",
            orientation="v",
            spacing=10,
            children=[
                Box(
                    name="subsection-heading-container",
                    h_expand=True,
                    v_expand=True,
                    children=[
                        Label(
                            name="subsection-heading-label",
                            label="Wi-Fi",
                            h_expand=True,
                            justification="left",
                            h_align="start",
                        ),
                        self.wifi_toggle,
                    ],
                ),
                # Box(
                #     name="subsection-heading-container",
                #     children=[Label(label="Connected", h_align="start")],
                # ),
                self.active_connection,
                Box(
                    name="subsection-heading-container",
                    children=[
                        Label(label="Available", h_align="start", h_expand=True),
                        Button(
                            h_align="end",
                            on_clicked=self.nm._schedule_scan_update,
                            child=Label(
                                style_classes=["menu-icon"], markup=icons.refresh
                            ),
                            tooltip_markup="Rescan",
                        ),
                    ],
                ),
                self.scrolled_container,
            ],
        )

        super().__init__(
            title="Internet",
            label="Wi-Fi",
            props=self.label,
            markup=icons.wifi,
            menu=True,
            menu_children=self.menu,
            style_classes=["off"],
            **kwargs,
        )

        # self._create_password_dialog()
        self._initialize_network_state()

    def _initialize_network_state(self):
        try:
            self.nm.init_props()
            self._is_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize network state: {e}")

    def _create_password_dialog(self):
        self._password_dialog = Window(
            name="password-dialog",
            layer="top",
            geometry="center",
            type_hint="normal",
            visible=False,
            all_visible=False,
            size=(300, 100),
        )

        password_entry = Entry(
            placeholder_text="Password",
            visibility=False,  # Hide password
            activates_default=True,  # Enter key triggers default button
        )
        self.box = Box(
            name="password-dialog-box",
            children=[Label(label="hello everyone"), self._password_dialog],
        )
        self._password_dialog.children = self.box

    def _do_toggle_wifi(self, switch: Gtk.Switch, pspec):
        if not self._is_initialized:
            return

        try:
            enabled = switch.get_active()
            success = self.nm.toggle_wifi_radio(enabled=enabled)

            if not success:
                # revert toggle on failure
                switch.set_active(not enabled)
                logger.error("Failed to toggle WiFi radio")

        except Exception as e:
            logger.error(f"Error toggling WiFi: {e}")
            switch.set_active(not switch.get_active())

    def on_ap_change(self):
        try:
            wifi_list = self.nm.get_wifi_list()
            self._update_network_lists(wifi_list)
        except Exception as e:
            logger.error(f"Error updating access point list: {e}")
            self._clear_network_lists()

    def _clear_network_lists(self):
        for container in [self.active_connection, self.connection_container]:
            for child in container.get_children():
                child.destroy()

    def _update_network_lists(self, wifi_list: list):
        self._clear_network_lists()

        if not wifi_list:
            self._show_empty_list()
            return

        active_networks = []
        available_networks = []

        for network in wifi_list:
            try:
                if not network.get("ssid"):
                    continue

                button = add_hover_cursor(
                    widget=WifiButton(
                        ap=network,
                        network_service=self.nm,
                        on_connect=self._handle_network_connect,
                    )
                )

                if network.get("active", False):
                    active_networks.append(button)
                else:
                    available_networks.append(button)

            except Exception as e:
                logger.error(
                    f"Error creating button for network {network.get('ssid', 'Unknown')}: {e}"
                )

        for button in active_networks:
            self.active_connection.add(button)

        available_networks.sort(key=lambda btn: btn.ap.get("strength", 0), reverse=True)

        for button in available_networks:
            self.connection_container.add(button)

    def _show_empty_list(self):
        empty_label = Label(
            label="No networks found", style_classes=["dim-label"], h_align="center"
        )
        self.connection_container.add(empty_label)

    def _show_error_state(self, message: str):
        self.label.set_label("Error")
        self.remove_style_class("on")
        self.add_style_class("off")

    def _handle_network_connect(self, ssid: str, password: Optional[str] = None):
        try:
            result = self.nm.connect_to_network(ssid, password)

            if result == ConnectionResult.PASSWORD_REQUIRED:
                ...
                self._show_password_dialog(ssid)
            elif result == ConnectionResult.ALREADY_CONNECTED:
                print(f"Already connected to {ssid}")
            elif result == ConnectionResult.NETWORK_NOT_FOUND:
                self._show_notification(f"Network '{ssid}' not found")
            elif result == ConnectionResult.NO_DEVICE:
                self._show_notification("No WiFi device available")
            elif result == ConnectionResult.DEVICE_BUSY:
                self._show_notification("Device is busy, please wait")
            elif result == ConnectionResult.CONNECTION_FAILED:
                self._show_notification(f"Failed to connect to '{ssid}'")
            elif result == ConnectionResult.INVALID_PASSWORD:
                self._show_notification("Invalid password format")
            elif result == ConnectionResult.SUCCESS:
                self._show_notification(f"Connecting to {ssid}...")

        except Exception as e:
            print(f"Error handling network connection: {e}")
            self._show_notification("Connection error occurred")

    def _show_password_dialog(self, ssid: str, error_message: Optional[str] = None):
        print("yezzir")
        # self._password_dialog.show_all()
        # self._password_dialog.set_visible(True)
        if self._password_dialog:
            self._password_dialog.destroy()

        # Create dialog
        self._password_dialog = Gtk.Dialog(
            title=f"Connect to {ssid}",
            transient_for=self.get_toplevel(),
            modal=True,
        )
        self._password_dialog.set_default_size(300, -1)
        self._password_dialog.set_visual(
            self._password_dialog.get_screen().get_rgba_visual()
        )
        self._password_dialog.set_position(Gtk.WindowPosition.CENTER)

        # Get content area
        content = self._password_dialog.get_content_area()
        content.set_name("password-dialog-box")
        content_box = Box(name="password-dialog-box", orientation="v", spacing=10)
        content.add(content_box)

        # Add error label if provided
        if error_message:
            error_label = Label(
                label=error_message, style_classes=["error-label"], h_align="start"
            )
            content_box.add(error_label)

        # ssid label
        ssid_label = Label(label=f"Enter password for '{ssid}':", h_align="start")
        content_box.add(ssid_label)

        # password entry
        password_entry = Entry(
            name="password-dialog-entry",
            placeholder_text="Password",
            visibility=False,  
            activates_default=True,  # Enter key triggers default button
        )
        content_box.add(password_entry)

        # show password checkbox
        show_password_check = Gtk.CheckButton(label="Show password")
        show_password_check.connect(
            "toggled", lambda btn: password_entry.set_visibility(btn.get_active())
        )
        content_box.add(show_password_check)

        # Add buttons
        cancel_btn = self._password_dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        cancel_btn.set_name("dialog-btn")
        connect_btn = connect_button = self._password_dialog.add_button(
            "Connect", Gtk.ResponseType.OK
        )
        connect_btn.set_name("dialog-btn")
        connect_button.get_style_context().add_class("suggested-action")
        self._password_dialog.set_default_response(Gtk.ResponseType.OK)

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                password = password_entry.get_text()
                if password:
                    self._handle_network_connect(ssid, password)
                else:
                    self._show_notification("Password cannot be empty")
            dialog.destroy()
            self._password_dialog = None

        self._password_dialog.connect("response", on_response)

        self._password_dialog.show_all()

    def _show_notification(self, message: str):
        exec_shell_command_async(f"notify-send NM-Service '{message}'")

    def _on_connection_change(
        self, source, con_label: str, connected: bool, status: str
    ):
        # visuals
        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            print("State change:", connected)

        # labels
        if not connected:
            label_map = {
                "Wi-Fi Off": "Off",
                "Wi-Fi On (No Connection)": "Disconnected",
                "Connecting…": "Connecting…",
                "No Device": "No Device",
            }
            self.label.set_label(label_map.get(status, "Unknown"))
        else:
            self.label.set_label(con_label or "Connected")

        # switch
        self._update_wifi_toggle_state(status)

    def _update_wifi_toggle_state(self, status: str):
        if status == "Wi-Fi Off":
            self.wifi_toggle.set_active(False)
        elif status in ["Wi-Fi On (No Connection)", "Connecting…", "Connected"]:
            self.wifi_toggle.set_active(True)

    def _on_connection_result(
        self, source, ssid: str, result: ConnectionResult, message: str
    ):
        ...
        # if result == ConnectionResult.INVALID_PASSWORD:
        #     # Show password dialog again with error message
        #     self._show_password_dialog(ssid, error_message="Incorrect password")
        # elif result == ConnectionResult.CONNECTION_FAILED:
        #     self._show_notification(f"Failed to connect to '{ssid}': {message}")
        # elif result == ConnectionResult.SUCCESS:
        #     print(f"Successfully connected to {ssid}")
        #     # Close password dialog if open
        #     if self._password_dialog:
        #         self._password_dialog.destroy()
        #         self._password_dialog = None


class WifiButton(EventBox):
    def __init__(
        self,
        ap: dict,
        on_connect: callable,
        network_service: NetworkService = None,
        **kwargs,
    ):
        self.ap = ap
        self.nm = network_service
        self.on_connect = on_connect
        self._context_menu = None

        super().__init__( 
            events=["button-press", "button-release", "enter-notify"],
            # on_clicked=lambda: self._on_clicked(),
            **kwargs,
        )

        self.connect("button-press-event", self._on_clicked)

        self.ssid = self.ap.get("ssid", "Unknown Network")
        self.strength = self.ap.get("strength", 0)
        self.secured = self.ap.get("secured", False)
        self.active = self.ap.get("active", False)

        self.is_saved = False
        if self.nm:
            saved_networks = self.nm.get_saved_networks()
            self.is_saved = self.ssid in saved_networks

        self.label_box = Box(
            orientation="v",
            h_expand=True,
            v_align="center",
            children=[
                Label(name="ap-label", label=self.ssid, h_align="start"),
            ],
        )
        self.status_label = Label(
            name="ap-label", label="Connecting...", h_align="start"
        )

        # print(self.ssid, ap["ssid"], '\n strength',self.strength,'\n active', ap["active"], '\n secured',self.secured, "\n")

        children = [
            Label(markup=self._get_wifi_icon(strength=self.strength)),
            self.label_box,
        ]

        if self.is_saved and not self.ap.get("active", False):
            children.append(
                Label(
                    markup=icons.sync_saved_locally,
                    tooltip_text="Saved",
                )
            )

        if self.secured:
            children.append(
                Label(
                    markup=icons.lock,
                    style_classes=["ap-secure-icon"],
                    tooltip_text="Secured network",
                )
            )

        if self.is_saved and not self.ap.get("active", False):
            children.append(
                Button(
                    child=Label(
                        markup=icons.settings,
                        style_classes=["ap-secure-icon"],
                        tooltip_text="Edit profile",
                    ),
                    on_clicked=lambda: self._show_update_password_dialog(),
                )
            )
        self.content = Box(
            name="ap-button",spacing=10, children=children)
        
        self.children = self.content

        self.connect("button-press-event", self._on_button_press)
        self.connect("enter-notify-event", self.on_enter)
        self.connect("leave-notify-event", self.on_leave)

        if ap.get("active", False):
            self.add_style_class("active")

    def on_enter(self, widget, event):
        self.content.add_style_class("hover")
        
    def on_leave(self, widget, event):
        if (event.detail == Gdk.NotifyType.INFERIOR):
            return
        self.content.remove_style_class("hover")

    def _get_wifi_icon(self, strength: int) -> str:
        if strength > 80:
            return icons.wifi_4
        elif strength > 50:
            return icons.wifi_3
        elif strength > 20:
            return icons.wifi_2
        else:
            return icons.wifi_1

    def _on_clicked(self, *args):
        try:
            if not self.ssid:
                logger.error("Cannot connect: No SSID")
                return

            if self.secured:
                logger.debug(f"Connecting to secured network: {self.ssid}")

            self.label_box.add(self.status_label)

            self.on_connect(self.ssid)

        except Exception as e:
            print(f"Error in WiFi button click: {e}")

    def _on_button_press(self, source, event):
        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False
    
    def _show_update_password_dialog(self):
        ssid = self.ap.get("ssid")
        if not ssid:
            logger.error("Cannot show update dialog: no SSID")
            return
        
        # Clean up existing dialog if present
        if hasattr(self, '_update_dialog') and self._update_dialog:
            self._update_dialog.destroy()
        
        # Create dialog
        self._update_dialog = Gtk.Dialog(
            title=f"Update Password for {ssid}",
            transient_for=self.get_toplevel(),
            modal=True,
        )
        self._update_dialog.set_default_size(350, -1)
        self._update_dialog.set_visual(
            self._update_dialog.get_screen().get_rgba_visual()
        )
        self._update_dialog.set_position(Gtk.WindowPosition.CENTER)
        
        # Get content area
        content = self._update_dialog.get_content_area()
        content.set_name("password-dialog-box")
        content_box = Box(name="password-dialog-box", orientation="v", spacing=10)
        content.add(content_box)
        
        # Add info label
        info_label = Label(
            label=f"Update saved password for '{ssid}':",
            h_align="start"
        )
        content_box.add(info_label)
        
        # Add password entry
        password_entry = Entry(
            name="password-dialog-entry",
            placeholder_text="New Password",
            visibility=False,
            activates_default=True,
        )
        content_box.add(password_entry)
        
        # Add show password checkbox
        show_password_check = Gtk.CheckButton(label="Show password")
        show_password_check.connect(
            "toggled", 
            lambda btn: password_entry.set_visibility(btn.get_active())
        )
        content_box.add(show_password_check)
        
        # Add warning label
        warning_label = Label(
            label="Note: This will update the saved network profile.",
            style_classes=["dim-label"],
            h_align="start"
        )
        content_box.add(warning_label)
        
        # Add buttons
        cancel_btn = self._update_dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        cancel_btn.set_name("dialog-btn")
        
        save_btn = self._update_dialog.add_button("Save", Gtk.ResponseType.OK)
        save_btn.set_name("dialog-btn")
        save_btn.get_style_context().add_class("suggested-action")
        self._update_dialog.set_default_response(Gtk.ResponseType.OK)
        self._update_dialog.show_all()
        
        # Connect response handler
        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                new_password = password_entry.get_text()
                
                if not new_password:
                    # Show error for empty password
                    error_dialog = Gtk.MessageDialog(
                        transient_for=dialog,
                        modal=True,
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text="Password cannot be empty"
                    )
                    error_dialog.format_secondary_text(
                        "Please enter a password or cancel."
                    )
                    error_dialog.run()
                    error_dialog.destroy()
                    return  # Don't close the dialog
                
                # Update the password
                if self.nm:
                    success = self._update_saved_password(ssid, new_password)
                    if success:
                        logger.info(f"Successfully updated password for {ssid}")
                        # Show success notification
                        exec_shell_command_async(
                            f"notify-send 'Network Updated' 'Password for {ssid} has been updated'"
                        )
                    else:
                        logger.error(f"Failed to update password for {ssid}")
                        # Show error notification
                        exec_shell_command_async(
                            f"notify-send 'Update Failed' 'Could not update password for {ssid}'"
                        )
            
            dialog.destroy()
            self._update_dialog = None
        
        self._update_dialog.connect("response", on_response)
        
        # Show dialog
        self._update_dialog.show_all()


    def _update_saved_password(self, ssid: str, new_password: str) -> bool:
        if not self.nm:
            logger.error("Cannot update password: no NetworkService")
            return False
        
        try:
            # Find the connection for this SSID
            connection = self.nm._find_connection_by_ssid(ssid)
            
            if not connection:
                logger.error(f"No saved connection found for {ssid}")
                return False
            
            # Update the password using NetworkService method
            success = self.nm._update_connection_password(connection, new_password)
            
            if success:
                logger.info(f"Password updated for {ssid}")
                return True
            else:
                logger.error(f"Failed to update password for {ssid}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating password for {ssid}: {e}")
            return False

    def _show_context_menu(self, event):
        menu = Gtk.Menu()

        if not self.active:
            connect_item = Gtk.MenuItem(label="Connect")
            connect_item.connect("activate", lambda *_: self._on_clicked())
            menu.append(connect_item)
        else:
            disconnect_item = Gtk.MenuItem(label="Disconnect")
            disconnect_item.connect("activate", lambda *_: self._disconnect_network())
            menu.append(disconnect_item)

        if self.is_saved:
            menu.append(Gtk.SeparatorMenuItem())
            forget_item = Gtk.MenuItem(label="Forget Network")
            forget_item.connect("activate", lambda *_: self._forget_network())
            menu.append(forget_item)

        menu.append(Gtk.SeparatorMenuItem())
        properties_item = Gtk.MenuItem(label="Properties")
        properties_item.connect("activate", lambda *_: self._show_properties())
        menu.append(properties_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _forget_network(self):
        ssid = self.ap.get("ssid")
        if not ssid or not self.nm:
            return

        # Show confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Forget network '{ssid}'?",
        )
        dialog.format_secondary_text(
            "This will remove the saved password and settings for this network."
        )

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            success = self.nm.forget_network(ssid)
            if success:
                print(f"Forgot network: {ssid}")
            else:
                print(f"Failed to forget network: {ssid}")

    def _show_properties(self):
        ssid = self.ap.get("ssid", "Unknown")
        strength = self.ap.get("strength", 0)
        frequency = self.ap.get("frequency", 0)
        secured = self.ap.get("secured", False)
        bssid = self.ap.get("bssid", "Unknown")

        # Format frequency
        freq_ghz = frequency / 1000 if frequency else 0
        band = "5 GHz" if freq_ghz >= 5 else "2.4 GHz" if freq_ghz >= 2 else "Unknown"

        properties_text = f"""
            Network: {ssid}
            Signal Strength: {strength}%
            Frequency: {freq_ghz:.1f} GHz ({band})
            Security: {"Secured" if secured else "Open"}
            BSSID: {bssid}
            """

        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=f"Network Properties",
        )
        dialog.set_visual(dialog.get_screen().get_rgba_visual())
        dialog.format_secondary_text(properties_text.strip())
        dialog.run()
        dialog.destroy()

    def _disconnect_network(self):
        if self.nm:
            success = self.nm.disconnect()
            if success:
                logger.info(f"Disconnecting from {self.ap.get('ssid')}")
            else:
                logger.warning("Failed to disconnect")
