from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scrolledwindow import ScrolledWindow

from fabric.utils.helpers import exec_shell_command_async

from modules.tile import Tile
from widgets.clipping_box import ClippingBox
from utils.cursor import add_hover_cursor
from services.network.network_service import NetworkService, ConnectionResult

from typing import Any

import icons

from loguru import logger
from typing import Optional, Callable, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


class UIConstants:
    WINDOW_MAX_WIDTH = 250
    WINDOW_MAX_HEIGHT = 250
    MAX_SSID_DISPLAY_LENGTH = 8
    DIALOG_DEFAULT_WIDTH = 350
    UPDATE_DIALOG_WIDTH = 350


class BaseDialog(Gtk.Dialog):
    def __init__(
        self, 
        parent_widget: Gtk.Widget, 
        title: str, 
        width: int = UIConstants.DIALOG_DEFAULT_WIDTH
    ):
        super().__init__(
            title=title,
            transient_for=parent_widget.get_toplevel(),
            modal=True
        )
        self.set_default_size(width, -1)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_content_area().set_spacing(10)
        self.get_content_area().set_name("password-dialog-box")
        self.set_default_response(Gtk.ResponseType.OK)
    
    def add_dialog_buttons(self, *labels: str) -> List[Gtk.Button]:
        buttons = []
        for i, label in enumerate(labels):
            response = Gtk.ResponseType.OK if i == len(labels) - 1 else Gtk.ResponseType.CANCEL
            btn = self.add_button(label, response)
            btn.set_name("dialog-btn")
            if response == Gtk.ResponseType.OK:
                btn.get_style_context().add_class("suggested-action")
            buttons.append(btn)
        return buttons
    
    def show_error_message(self, text: str, secondary_text: str = "") -> None:
        error_dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=text
        )
        if secondary_text:
            error_dialog.format_secondary_text(secondary_text)
        error_dialog.run()
        error_dialog.destroy()
    
    @staticmethod
    def show_notification(title: str, message: str = "") -> None:
        if message:
            exec_shell_command_async(f"notify-send '{title}' '{message}'")
        else:
            exec_shell_command_async(f"notify-send 'NM-Service' '{title}'")


class PasswordDialog(BaseDialog):
    """Password entry dialog for connecting to or updating networks."""
    
    def __init__(
        self,
        parent_widget: Gtk.Widget,
        ssid: str,
        on_submit: Callable[[str], None],
        error_message: Optional[str] = None,
        update_mode: bool = False
    ):
        title = f"{'Update Password for' if update_mode else 'Connect to'} {ssid}"
        super().__init__(parent_widget, title, UIConstants.DIALOG_DEFAULT_WIDTH)
        
        self.ssid = ssid
        self.on_submit = on_submit
        self.update_mode = update_mode
        
        self._build_ui(error_message)
        self.connect("response", self._on_response)
        self.show_all()
    
    def _build_ui(self, error_message: Optional[str]) -> None:
        content_box = Box(name="password-dialog-box", orientation="v", spacing=10)
        self.get_content_area().add(content_box)
        
        if error_message:
            content_box.add(Label(
                label=error_message,
                style_classes=["error-label"],
                h_align="start"
            ))
        
        info_text = (
            f"Update saved password for '{self.ssid}':" 
            if self.update_mode 
            else f"Enter password for '{self.ssid}':"
        )
        content_box.add(Label(label=info_text, h_align="start"))
        
        self.password_entry = Entry(
            name="password-dialog-entry",
            placeholder_text="New Password" if self.update_mode else "Password",
            visibility=False,
            activates_default=True
        )
        content_box.add(self.password_entry)
        
        show_password = Gtk.CheckButton(label="Show password")
        show_password.connect(
            "toggled",
            lambda btn: self.password_entry.set_visibility(btn.get_active())
        )
        content_box.add(show_password)
        
        if self.update_mode:
            content_box.add(Label(
                label="Note: This will update the saved network profile.",
                style_classes=["dim-label"],
                h_align="start"
            ))
        
        self.add_dialog_buttons("Cancel", "Save" if self.update_mode else "Connect")
    
    def _on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            password = self.password_entry.get_text()
            
            if not password:
                self.show_error_message(
                    "Password cannot be empty",
                    "Please enter a password or cancel."
                )
                return  # don't close dialog
            
            self.on_submit(password)
        
        self.destroy()


class ConfirmDialog(BaseDialog):
    """Confirmation dialog for destructive actions."""

    def __init__(
        self,
        parent_widget: Gtk.Widget,
        title: str,
        message: str,
        secondary: str,
        on_confirm: Callable[[], None],
        confirm_label: str = "Confirm"
    ):
        super().__init__(parent_widget, title)
        
        self.on_confirm = on_confirm
        
        self._build_ui(message, secondary, confirm_label)
        self.connect("response", self._on_response)
        self.show_all()
    
    def _build_ui(self, message: str, secondary: str, confirm_label: str) -> None:
        box = Box(name="confirm-dialog-box", orientation="v", spacing=10)
        self.get_content_area().add(box)
        
        box.add(Label(label=message, h_align="start"))
        box.add(Label(label=secondary, h_align="start", wrap=True))
        
        self.add_dialog_buttons("Cancel", confirm_label)
    
    def _on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            self.on_confirm()
        self.destroy()


class PropertiesDialog(BaseDialog):
    """Network properties display dialog."""
    
    def __init__(self, parent_widget: Gtk.Widget, ap: dict):
        ssid = ap.get("ssid", "Unknown")
        super().__init__(parent_widget, f"Properties: {ssid}")
        
        self._build_ui(ap)
        self.show_all()
    
    def _build_ui(self, ap: dict) -> None:
        ssid = ap.get("ssid", "Unknown")
        strength = ap.get("strength", 0)
        frequency = ap.get("frequency", 0)
        secured = ap.get("secured", False)
        bssid = ap.get("bssid", "Unknown")
        
        freq_ghz = frequency / 1000 if frequency else 0
        
        if freq_ghz >= 5:
            band = "5 GHz"
        elif freq_ghz >= 2:
            band = "2.4 GHz"
        else:
            band = "Unknown"
        
        properties = {
            "Network": ssid,
            "Signal Strength": f"{strength}%",
            "Frequency": f"{freq_ghz:.1f} GHz ({band})",
            "Security": "Secured" if secured else "Open",
            "BSSID": bssid,
        }
        
        content_box = Box(name="password-dialog-box", orientation="v", spacing=10)
        self.get_content_area().add(content_box)
        
        for label, value in properties.items():
            row = Box(
                spacing=10,
                children=[
                    Label(
                        label=label,
                        style_classes=["error-label"],
                        h_align="start",
                        h_expand=True
                    ),
                    Label(label=value, h_align="end")
                ]
            )
            content_box.add(row)
        
        buttons = Box(orientation="h", spacing=8, h_align="end")
        content_box.add(buttons)
        
        close_btn = Button(name="dialog-btn", label="Close")
        close_btn.connect("clicked", lambda *_: self.destroy())
        buttons.add(close_btn)


class WifiButton(EventBox):
    def __init__(
        self,
        ap: dict,
        network_service: NetworkService,
        on_connect: Callable[[str, Optional[str]], None],
        **kwargs,
    ):
        self.ap = ap
        self.nm = network_service
        self.on_connect = on_connect

        super().__init__(
            events=["button-press", "button-release", "enter-notify", "leave-notify"],
            **kwargs,
        )

        self.ssid = self.ap.get("ssid", "Unknown Network")
        self.strength = self.ap.get("strength", 0)
        self.secured = self.ap.get("secured", False)
        self.active = self.ap.get("active", False)
        self.is_saved = self.ssid in self.nm.get_saved_networks()

        self._build_ui()

        self.connect("button-press-event", self._on_button_press)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        if self.active:
            self.add_style_class("active")

    def _build_ui(self) -> None:
        self.label_box = Box(
            orientation="v",
            h_expand=True,
            v_align="center",
            children=[Label(name="ap-label", label=self.ssid, h_align="start")],
        )

        self.status_label = Label(
            name="ap-label", label="Connecting...", h_align="start"
        )

        children = [Label(markup=self._get_wifi_icon()), self.label_box]

        if self.is_saved and not self.active:
            children.append(
                Label(markup=icons.sync_saved_locally, tooltip_text="Saved")
            )

        if self.secured:
            children.append(
                Label(
                    markup=icons.lock,
                    style_classes=["ap-secure-icon"],
                    tooltip_text="Secured network",
                )
            )

        if self.is_saved and not self.active:
            children.append(
                Button(
                    child=Label(
                        markup=icons.settings,
                        style_classes=["ap-secure-icon"],
                        tooltip_text="Edit profile",
                    ),
                    on_clicked=self._show_update_password_dialog,
                )
            )

        self.content = Box(name="ap-button", spacing=10, children=children)
        self.children = self.content

    def _get_wifi_icon(self) -> str:
        if self.strength > 80:
            return icons.wifi_4
        elif self.strength > 50:
            return icons.wifi_3
        elif self.strength > 20:
            return icons.wifi_2
        else:
            return icons.wifi_1

    def _on_button_press(self, source: EventBox, event: Gdk.EventButton) -> bool:
        if event.button == 1:  # left click
            self._do_connect()
            return True
        elif event.button == 3:  # right click
            self._show_context_menu(event)
            return True
        return False

    def _do_connect(self) -> None:
        if not self.ssid:
            logger.error("Cannot connect: No SSID")
            return

        try:
            logger.debug(f"Connecting to: {self.ssid}")
            self.label_box.add(self.status_label)
            self.on_connect(self.ssid, None)
        except Exception as e:
            logger.error(f"Error in WiFi button click: {e}")

    def _on_enter(self, widget: EventBox, event: Gdk.EventCrossing) -> None:
        self.content.add_style_class("hover")

    def _on_leave(self, widget: EventBox, event: Gdk.EventCrossing) -> None:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self.content.remove_style_class("hover")

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        if not self.active:
            connect_item = Gtk.MenuItem(label="Connect")
            connect_item.connect("activate", lambda *_: self._do_connect())
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

    def _show_update_password_dialog(self, *args) -> None:
        if not self.ssid:
            logger.error("Cannot show update dialog: no SSID")
            return
        
        def on_update(password: str):
            success = self._update_saved_password(password)
            if success:
                BaseDialog.show_notification(
                    "Network Updated",
                    f"Password for {self.ssid} has been updated"
                )
            else:
                BaseDialog.show_notification(
                    "Update Failed",
                    f"Could not update password for {self.ssid}"
                )
        
        PasswordDialog(self, self.ssid, on_update, update_mode=True)

    def _update_saved_password(self, new_password: str) -> bool:
        try:
            connection = self.nm.profile_manager.find_by_ssid(self.ssid)

            if not connection:
                logger.error(f"No saved connection found for {self.ssid}")
                return False

            success = self.nm.profile_manager.update_password(connection, new_password)

            if success:
                logger.info(f"Password updated for {self.ssid}")
            else:
                logger.error(f"Failed to update password for {self.ssid}")

            return success

        except Exception as e:
            logger.error(f"Error updating password for {self.ssid}: {e}")
            return False

    def _forget_network(self) -> None:
        if not self.ssid:
            return
        
        def on_confirm():
            success = self.nm.forget_network(self.ssid)
            if success:
                logger.info(f"Forgot network: {self.ssid}")
            else:
                logger.error(f"Failed to forget network: {self.ssid}")
        
        ConfirmDialog(
            self,
            title=f"Forget '{self.ssid}'?",
            message=f"Forget network '{self.ssid}'?",
            secondary="This will remove the saved password and settings for this network.",
            on_confirm=on_confirm,
            confirm_label="Forget"
        )

    def _show_properties(self) -> None:
        PropertiesDialog(self, self.ap)

    def _disconnect_network(self) -> None:
        success = self.nm.disconnect()
        if success:
            logger.info(f"Disconnecting from {self.ssid}")
        else:
            logger.warning("Failed to disconnect")


class NetworkListManager:
    def __init__(
        self,
        active_container: Box,
        available_container: Box,
        network_service: NetworkService,
        on_connect: Callable[[str, Optional[str]], None],
    ):
        self.active_container = active_container
        self.available_container = available_container
        self.nm = network_service
        self.on_connect = on_connect

    def update(self, wifi_list: List[dict]) -> None:
        self._clear()

        if not wifi_list:
            self._show_empty_state()
            return

        active_networks = []
        available_networks = []

        for network in wifi_list:
            if not network.get("ssid"):
                continue

            try:
                button = add_hover_cursor(
                    widget=WifiButton(
                        ap=network, network_service=self.nm, on_connect=self.on_connect
                    )
                )

                if network.get("active", False):
                    active_networks.append(button)
                else:
                    available_networks.append(button)

            except Exception as e:
                logger.error(
                    f"Error creating button for {network.get('ssid', 'Unknown')}: {e}"
                )

        for button in active_networks:
            self.active_container.add(button)

        available_networks.sort(key=lambda btn: btn.ap.get("strength", 0), reverse=True)
        for button in available_networks:
            self.available_container.add(button)

    def _clear(self) -> None:
        for container in [self.active_container, self.available_container]:
            for child in container.get_children():
                child.destroy()

    def _show_empty_state(self) -> None:
        empty_label = Label(
            label="No networks found", style_classes=["dim-label"], h_align="center"
        )
        self.available_container.add(empty_label)


class Network(Tile):
    def __init__(self, **kwargs):
        self.state: Optional[bool] = None
        self._is_initialized = False

        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
            ellipsization="end",
            max_chars_width=UIConstants.MAX_SSID_DISPLAY_LENGTH,
        )

        self.nm = NetworkService()
        self.nm.connect("connection-change", self._on_connection_change)
        self.nm.connect("ap-change", self._on_ap_change)
        self.nm.connect("connection-result", self._on_connection_result)

        self.wifi_toggle = Gtk.Switch(name="matugen-switcher")
        self.wifi_toggle.set_active(True)
        self.wifi_toggle.connect("notify::active", self._do_toggle_wifi)
        self.wifi_toggle.set_visible(True)

        self.active_connection = ClippingBox(
            name="network-scrolled-window-container", orientation="v", children=[]
        )

        self.connection_container = Box(
            name="connection-container", orientation="v", spacing=2, children=[]
        )

        self.scrolled_container = ClippingBox(
            name="network-scrolled-window-container",
            children=ScrolledWindow(
                name="network-scrolled-window",
                h_expand=True,
                max_content_size=(
                    UIConstants.WINDOW_MAX_WIDTH,
                    UIConstants.WINDOW_MAX_HEIGHT,
                ),
                h_scrollbar_policy="external",
                v_scrollbar_policy="external",
                child=self.connection_container,
            ),
        )

        self.menu = self._build_menu()

        self.list_manager = NetworkListManager(
            self.active_connection,
            self.connection_container,
            self.nm,
            self._handle_network_connect,
        )

        self.password_dialog: Optional[PasswordDialog] = None

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

        self._initialize_network_state()

    def _build_menu(self) -> Box:
        return Box(
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
                self.active_connection,
                Box(
                    name="subsection-heading-container",
                    children=[
                        Label(label="Available", h_align="start", h_expand=True),
                        Button(
                            h_align="end",
                            on_clicked=lambda *_: self.nm.scan(),
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

    def _initialize_network_state(self) -> None:
        try:
            self.nm.init_props()
            self._is_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize network state: {e}")

    def _do_toggle_wifi(self, switch: Gtk.Switch, pspec: Any) -> None:
        if not self._is_initialized:
            return

        try:
            enabled = switch.get_active()
            success = self.nm.toggle_wifi_radio(enabled=enabled)

            if not success:
                # revert toggle
                switch.set_active(not enabled)
                logger.error("Failed to toggle WiFi radio")

        except Exception as e:
            logger.error(f"Error toggling WiFi: {e}")
            switch.set_active(not switch.get_active())

    def _on_ap_change(self, source: NetworkService) -> None:
        try:
            wifi_list = self.nm.get_wifi_list()
            self.list_manager.update(wifi_list)
        except Exception as e:
            logger.error(f"Error updating access point list: {e}")
            self.list_manager._clear()

    def _on_connection_change(
        self, source: NetworkService, ssid: str, connected: bool, status: str
    ) -> None:
        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            logger.debug(f"State change: {connected}")

        if not connected:
            label_map = {
                "Wi-Fi Off": "Off",
                "Wi-Fi On (No Connection)": "Disconnected",
                "Connecting…": "Connecting…",
                "No Device": "No Device",
            }
            self.label.set_label(label_map.get(status, "Unknown"))
        else:
            self.label.set_label(ssid or "Connected")

        self._update_wifi_toggle_state(status)

    def _update_wifi_toggle_state(self, status: str) -> None:
        if status == "Wi-Fi Off":
            self.wifi_toggle.set_active(False)
        elif status in ["Wi-Fi On (No Connection)", "Connecting…", "Connected"]:
            self.wifi_toggle.set_active(True)

    def _on_connection_result(
        self, source: NetworkService, ssid: str, result: ConnectionResult, message: str
    ) -> None:
        if result == ConnectionResult.INVALID_PASSWORD:
            self._show_password_dialog(ssid, "Incorrect password. Please try again.")

        elif result == ConnectionResult.SUCCESS:
            logger.info(f"Successfully connected to {ssid}")
            BaseDialog.show_notification(f"Connected to {ssid}")

            if self.password_dialog:
                self.password_dialog.destroy()
                self.password_dialog = None

    def _handle_network_connect(
        self, ssid: str, password: Optional[str] = None
    ) -> None:
        try:
            result = self.nm.connect_to_network(ssid, password)

            if result == ConnectionResult.PASSWORD_REQUIRED:
                self._show_password_dialog(ssid)

            elif result == ConnectionResult.ALREADY_CONNECTED:
                logger.info(f"Already connected to {ssid}")

            elif result == ConnectionResult.NETWORK_NOT_FOUND:
                BaseDialog.show_notification(f"Network '{ssid}' not found")

            elif result == ConnectionResult.NO_DEVICE:
                BaseDialog.show_notification("No WiFi device available")

            elif result == ConnectionResult.CONNECTION_FAILED:
                BaseDialog.show_notification(f"Failed to connect to '{ssid}'")

            elif result == ConnectionResult.SUCCESS:
                BaseDialog.show_notification(f"Connecting to {ssid}...")

        except Exception as e:
            logger.error(f"Error handling network connection: {e}")
            BaseDialog.show_notification("Connection error occurred")

    def _show_password_dialog(
        self, ssid: str, error_message: Optional[str] = None
    ) -> None:
        # clean up existing dialog
        if self.password_dialog:
            self.password_dialog.destroy()
            self.password_dialog = None

        def on_submit(password: str):
            self._handle_network_connect(ssid, password)

        self.password_dialog = PasswordDialog(
            self, ssid, on_submit, error_message, update_mode=False
        )