from typing import Any
from loguru import logger
from typing import ClassVar
from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.checkbutton import CheckButton
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.utils.helpers import exec_shell_command_async

import icons
from config.config import config
from modules.tile import TileSimpleWithMenu

from services.network.wifi import WifiDevice
from services.network.ethernet import EthernetDevice
from services.network.common import ConnectionResult, DeviceStatus, NetworkConstants
from services.network.network_service import NetworkService, ConnectionType

from utils.colors import bind_theme
from utils.cursor import add_hover_cursor
from utils.helpers import format_accel_to_keybind

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from widgets.tile_menu import (
    MIN_BUSY_MS,
    ContentFader,
    TileMenuLoader,
    menu_placeholder,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore


class UIConstants:
    WINDOW_MAX_WIDTH = 250
    WINDOW_MAX_HEIGHT = 260
    MAX_SSID_DISPLAY_LENGTH = 8
    DIALOG_DEFAULT_WIDTH = 350
    UPDATE_DIALOG_WIDTH = 350
    MAX_ROW_LABEL_CHARS = 26
    FAILURE_DISPLAY_MS = 6000


class BaseDialog(Gtk.Dialog):
    def __init__(
        self,
        parent_widget: Gtk.Widget,
        title: str,
        width: int = UIConstants.DIALOG_DEFAULT_WIDTH,
    ):
        super().__init__(
            title=title, transient_for=parent_widget.get_toplevel(), modal=True
        )
        bind_theme(self)
        self.set_default_size(width, -1)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_content_area().set_spacing(10)
        self.get_content_area().set_name("password-dialog-box")
        self.set_default_response(Gtk.ResponseType.OK)

    def add_dialog_buttons(self, *labels: str) -> list[Gtk.Button]:
        buttons = []
        for i, label in enumerate(labels):
            response = (
                Gtk.ResponseType.OK if i == len(labels) - 1 else Gtk.ResponseType.CANCEL
            )
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
            text=text,
        )
        if secondary_text:
            error_dialog.format_secondary_text(secondary_text)
        error_dialog.run()
        error_dialog.destroy()

    @staticmethod
    def show_notification(title: str, message: str = "") -> None:
        # argv, not a command line: SSIDs contain quotes and spaces. Escaped
        # because notification bodies are markup.
        summary, body = (title, message) if message else ("NM-Service", title)
        try:
            exec_shell_command_async(
                ["notify-send", summary, GLib.markup_escape_text(body)]
            )
        except GLib.Error as e:
            logger.warning(f"Could not send notification: {e}")


class PasswordDialog(BaseDialog):
    """Password entry dialog for connecting to or updating networks."""

    def __init__(
        self,
        parent_widget: Gtk.Widget,
        ssid: str,
        on_submit: Callable[[str], None],
        error_message: str | None = None,
        update_mode: bool = False,
    ):
        title = f"{'Update Password for' if update_mode else 'Connect to'} {ssid}"
        super().__init__(parent_widget, title, UIConstants.DIALOG_DEFAULT_WIDTH)

        self.ssid = ssid
        self.on_submit = on_submit
        self.update_mode = update_mode

        self._build_ui(error_message)
        self.connect("response", self._on_response)
        self.show_all()

    def _build_ui(self, error_message: str | None) -> None:
        content_box = Box(name="password-dialog-box", orientation="v", spacing=10)
        self.get_content_area().add(content_box)

        if error_message:
            content_box.add(
                Label(
                    label=error_message, style_classes=["error-label"], h_align="start"
                )
            )

        info_text = (
            f"Update saved password for '{self.ssid}':"
            if self.update_mode
            else f"Enter password for '{self.ssid}':"
        )
        content_box.add(Label(label=info_text, h_align="start"))

        self.password_entry = Entry(
            name="password-dialog-entry",
            placeholder_text="New Password" if self.update_mode else "Password",
            activates_default=True,
            password=True,
        )
        content_box.add(self.password_entry)

        show_password = CheckButton(name="show-password-check", label="Show password")
        show_password.connect(
            "toggled", lambda btn: self.password_entry.set_visibility(btn.get_active())
        )
        content_box.add(show_password)

        if self.update_mode:
            content_box.add(
                Label(
                    label="Note: This will update the saved network profile.",
                    style_classes=["dim-label"],
                    h_align="start",
                )
            )

        self.add_dialog_buttons("Cancel", "Save" if self.update_mode else "Connect")

    def _on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            password = self.password_entry.get_text()

            if not password:
                self.show_error_message(
                    "Password cannot be empty", "Please enter a password or cancel."
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
        confirm_label: str = "Confirm",
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


class BasePropertiesDialog(BaseDialog):
    def __init__(self, parent_widget: Gtk.Widget, data: dict):
        title = self.get_title_from_data(data)
        super().__init__(parent_widget, f"Properties: {title}")

        properties = self.get_properties(data)

        self._build_ui(properties)
        self.show_all()

    def get_title_from_data(self, data: dict) -> str:
        raise NotImplementedError("Subclasses must implement get_title_from_data")

    def get_properties(self, data: dict) -> dict:
        raise NotImplementedError("Subclasses must implement get_properties")

    def _build_ui(self, properties: dict) -> None:
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
                        h_expand=True,
                    ),
                    Label(label=str(value), h_align="end"),
                ],
            )
            content_box.add(row)

        buttons = Box(orientation="h", spacing=8, h_align="end")
        close_btn = Button(name="dialog-btn", label="Close")
        close_btn.connect("clicked", lambda *_: self.destroy())
        buttons.add(close_btn)
        content_box.add(buttons)


class PropertiesDialogEthernet(BasePropertiesDialog):
    def get_title_from_data(self, data: dict) -> str:
        return data.get("name", "Unknown")

    def get_properties(self, data: dict) -> dict:
        return {
            "Device/Connection ID": data.get("name", "Unknown"),
            "State": getattr(data.get("state"), "value", "Unknown"),
            "IFace": data.get("iface", "Unknown"),
        }


class PropertiesDialogWifi(BasePropertiesDialog):
    def get_title_from_data(self, data: dict) -> str:
        return data.get("ssid", "Unknown")

    def get_properties(self, data: dict) -> dict:
        freq = data.get("frequency", 0)
        freq_ghz = freq / 1000 if freq else 0
        band = "5 GHz" if freq_ghz >= 5 else "2.4 GHz" if freq_ghz >= 2 else "Unknown"

        return {
            "Network": data.get("ssid", "Unknown"),
            "Signal Strength": f"{data.get('strength', 0)}%",
            "Frequency": f"{freq_ghz:.1f} GHz ({band})",
            "Security": "Secured" if data.get("secured") else "Open",
            "BSSID": data.get("bssid", "Unknown"),
        }


def _row_action_button(
    icon: str, tooltip: str, on_clicked: Callable[..., None]
) -> tuple[Button, MaterialIconLabel]:
    icon_label = MaterialIconLabel(icon_text=icon, style_classes=["ap-action-icon"])
    button = add_hover_cursor(
        Button(
            style_classes=["ap-action-btn"],
            v_align="center",
            child=icon_label,
            tooltip_text=tooltip,
            on_clicked=on_clicked,
        )
    )
    # visibility follows the row state, opening the menu must not show_all() it
    button.set_no_show_all(True)
    icon_label.show()
    return button, icon_label


class WifiRowState:
    IDLE = "idle"
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"


class WifiButton(EventBox):
    def __init__(
        self,
        ap: dict,
        network_service: WifiDevice,
        on_connect: Callable[[str, str | None], None],
        on_disconnect: Callable[[], None],
        is_saved: bool = False,
        **kwargs,
    ):
        self.ap = ap
        self.nm = network_service
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.row_state = WifiRowState.IDLE

        super().__init__(
            events=["button-press", "button-release", "enter-notify", "leave-notify"],
            **kwargs,
        )

        self.ssid = self.ap.get("ssid", "Unknown Network")
        self.strength = self.ap.get("strength", 0)
        self.secured = self.ap.get("secured", False)
        self.is_saved = is_saved

        self._build_ui()

        self.connect("button-press-event", self._on_button_press)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        self.set_row_state(WifiRowState.IDLE)

    def _build_ui(self) -> None:
        self.status_label = Label(name="ap-status-label", h_align="start")
        self.label_box = Box(
            orientation="v",
            h_expand=True,
            v_align="center",
            children=[
                Label(
                    name="ap-label",
                    label=self.ssid,
                    h_align="start",
                    max_chars_width=UIConstants.MAX_ROW_LABEL_CHARS,
                    ellipsization="end",
                ),
                self.status_label,
            ],
        )

        self.wifi_icon = MaterialIconLabel(
            name="ap-icon", icon_text=self._get_wifi_icon(), h_expand=False
        )
        children = [self.wifi_icon, self.label_box]

        if self.secured:
            children.append(
                MaterialIconLabel(
                    icon_text=icons.material.lock.symbol(),
                    style_classes=["ap-secure-icon"],
                    tooltip_text="Secured network",
                )
            )

        self.edit_button, _ = _row_action_button(
            icons.material.key.symbol(),
            "Change password",
            self._show_update_password_dialog,
        )
        self.disconnect_button, self.disconnect_icon = _row_action_button(
            icons.material.link_off.symbol(),
            "Disconnect",
            lambda *_: self.on_disconnect(),
        )

        children += [self.edit_button, self.disconnect_button]

        self.content = Box(name="ap-button", spacing=10, children=children)
        self.children = self.content

    def _idle_status(self) -> str:
        if self.is_saved:
            return "Saved"
        return "Secured" if self.secured else "Open"

    def set_row_state(self, state: str, text: str | None = None) -> None:
        self.row_state = state
        self.status_label.set_label(text or self._idle_status())

        is_connecting = state == WifiRowState.CONNECTING
        if is_connecting:
            self.content.add_style_class("connecting")
        else:
            self.content.remove_style_class("connecting")

        is_online = state in (
            WifiRowState.CONNECTED,
            WifiRowState.CONNECTING,
            WifiRowState.DISCONNECTING,
        )
        has_edit_button = self.is_saved and not is_online
        self.edit_button.set_visible(has_edit_button)
        self.disconnect_button.set_visible(is_online)
        # round buttons sit closer to the edge than a bare icon should
        if has_edit_button or is_online:
            self.content.remove_style_class("no-action")
        else:
            self.content.add_style_class("no-action")
        self.disconnect_button.set_sensitive(state != WifiRowState.DISCONNECTING)
        self.disconnect_button.set_tooltip_text(
            "Cancel" if is_connecting else "Disconnect"
        )
        self.disconnect_icon.set_icon(
            icons.material.close.symbol()
            if is_connecting
            else icons.material.link_off.symbol()
        )

    @staticmethod
    def strength_bucket(strength: int) -> int:
        if strength > 80:
            return 4
        elif strength > 50:
            return 3
        elif strength > 20:
            return 2
        return 1

    def _get_wifi_icon(self) -> str:
        return {
            4: icons.material.wifi_4,
            3: icons.material.wifi_3,
            2: icons.material.wifi_2,
            1: icons.material.wifi_1,
        }[self.strength_bucket(self.strength)].symbol()

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

        if self.row_state not in (WifiRowState.IDLE, WifiRowState.FAILED):
            return

        try:
            logger.debug(f"Connecting to: {self.ssid}")
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

        if self.row_state in (WifiRowState.IDLE, WifiRowState.FAILED):
            connect_item = Gtk.MenuItem(label="Connect")
            connect_item.connect("activate", lambda *_: self._do_connect())
            menu.append(connect_item)
        else:
            disconnect_item = Gtk.MenuItem(
                label=(
                    "Cancel"
                    if self.row_state == WifiRowState.CONNECTING
                    else "Disconnect"
                )
            )
            disconnect_item.set_sensitive(self.row_state != WifiRowState.DISCONNECTING)
            disconnect_item.connect("activate", lambda *_: self.on_disconnect())
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
                    "Network Updated", f"Password for {self.ssid} has been updated"
                )
            else:
                BaseDialog.show_notification(
                    "Update Failed", f"Could not update password for {self.ssid}"
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
            confirm_label="Forget",
        )

    def _show_properties(self) -> None:
        PropertiesDialogWifi(self, self.ap)


class EthernetButton(EventBox):
    # NM calls a wired device "unavailable" when there's no carrier
    STATUS_LABELS: ClassVar = {
        DeviceStatus.UNKNOWN: "Unavailable",
        DeviceStatus.DEVICE_OFF: "Cable unplugged",
        DeviceStatus.DISCONNECTED: "Disconnected",
        DeviceStatus.CONNECTING: "Connecting…",
        DeviceStatus.CONNECTED: "Connected",
        DeviceStatus.DISCONNECTING: "Disconnecting…",
        DeviceStatus.FAILED: "Connection failed",
        DeviceStatus.NO_DEVICE: "No Device",
    }

    def __init__(
        self,
        eth_conn: dict,
        network_service: NetworkService,
        on_state_change: Callable[[], None] = lambda: None,
        **kwargs,
    ):
        self.eth_conn = eth_conn
        self.nm = network_service
        self.on_state_change = on_state_change
        self.device: EthernetDevice = eth_conn.get("device", None)

        super().__init__(
            events=["button-press", "button-release", "enter-notify", "leave-notify"],
            **kwargs,
        )

        self.name = self.eth_conn.get("name", "Unknown")
        self.state = self.eth_conn.get("state", DeviceStatus.UNKNOWN)

        self._build_ui()

        self.connect("button-press-event", self._on_button_press)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        if self.device:
            # rows get rebuilt, the device outlives them
            state_handler = self.device.connect("state-changed", self._on_state_changed)
            self.connect("destroy", lambda *_: self.device.disconnect(state_handler))

    def _build_ui(self) -> None:
        self.status_label = Label(name="ap-status-label", h_align="start")
        self.label_box = Box(
            orientation="v",
            h_expand=True,
            v_align="center",
            children=[
                Label(
                    name="ap-label",
                    label=self.name,
                    h_align="start",
                    max_chars_width=UIConstants.MAX_ROW_LABEL_CHARS,
                    ellipsization="end",
                ),
                self.status_label,
            ],
        )

        self.disconnect_button, _ = _row_action_button(
            icons.material.link_off.symbol(),
            "Disconnect",
            lambda *_: self._disconnect_network(),
        )

        children = [
            MaterialIconLabel(
                name="ap-icon", icon_text=self._get_ethernet_icon(), h_expand=False
            ),
            self.label_box,
            self.disconnect_button,
        ]

        self.content = Box(name="ap-button", spacing=10, children=children)
        self.children = self.content
        self._show_status(self.state)

    def _get_ethernet_icon(self) -> str:
        return icons.material.lan.symbol()

    def _on_button_press(self, source: EventBox, event: Gdk.EventButton) -> bool:
        if event.button == 1:  # left click
            self._do_connect()
            return True
        elif event.button == 3:  # right click
            self._show_context_menu(event)
            return True
        return False

    def _on_state_changed(self, source, name, status):
        self.state = status
        self._show_status(status)
        self.on_state_change()

    def _show_status(self, status: DeviceStatus) -> None:
        self.status_label.set_label(self.STATUS_LABELS.get(status, "Unknown"))

        if status == DeviceStatus.CONNECTING:
            self.content.add_style_class("connecting")
        else:
            self.content.remove_style_class("connecting")

        self.disconnect_button.set_visible(
            status in (DeviceStatus.CONNECTED, DeviceStatus.CONNECTING)
        )

    def _can_connect(self) -> bool:
        return self.state in (DeviceStatus.DISCONNECTED, DeviceStatus.FAILED)

    def _do_connect(self) -> None:
        if not self.name:
            logger.error("Cannot connect: No connection name")
            return

        if not self._can_connect():
            return

        try:
            logger.debug(f"Connecting: {self.name}")
            self.device.connect_to_network()
        except Exception as e:
            logger.error(f"Error in WiFi button click: {e}")

    def _disconnect_network(self) -> None:
        success = self.device.disconnect_network()
        if success:
            logger.info(f"Disconnecting from {self.name}")
        else:
            logger.warning("Failed to disconnect")

    def _on_enter(self, widget: EventBox, event: Gdk.EventCrossing) -> None:
        self.content.add_style_class("hover")

    def _on_leave(self, widget: EventBox, event: Gdk.EventCrossing) -> None:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self.content.remove_style_class("hover")

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        is_connected = self.state in (DeviceStatus.CONNECTED, DeviceStatus.CONNECTING)
        if not is_connected:
            connect_item = Gtk.MenuItem(label="Connect")
            connect_item.set_sensitive(self._can_connect())
            connect_item.connect("activate", lambda *_: self._do_connect())
            menu.append(connect_item)
        else:
            disconnect_item = Gtk.MenuItem(label="Disconnect")
            disconnect_item.connect("activate", lambda *_: self._disconnect_network())
            menu.append(disconnect_item)

        menu.append(Gtk.SeparatorMenuItem())
        properties_item = Gtk.MenuItem(label="Properties")
        properties_item.connect("activate", lambda *_: self._show_properties())
        menu.append(properties_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _show_properties(self) -> None:
        PropertiesDialogEthernet(self, self.eth_conn)


class NetworkListManager:
    def __init__(
        self,
        active_container: Box,
        available_container: Box,
        network_service: WifiDevice | None,
        on_connect: Callable[[str, str | None], None],
        on_disconnect: Callable[[], None],
    ):
        self.active_container = active_container
        self.available_container = available_container
        self.nm = network_service
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.rows: dict[str, WifiButton] = {}

    @staticmethod
    def make_signature(
        wifi_list: list[dict], saved: set[str], empty_text: str
    ) -> tuple:
        """Everything that's fixed once a row is built, in display order."""
        rows = tuple(
            (
                network.get("ssid"),
                network.get("active", False),
                network.get("secured", False),
                network.get("ssid") in saved,
                WifiButton.strength_bucket(network.get("strength", 0)),
            )
            for network in wifi_list
        )
        return (rows, empty_text if not rows else "")

    def update(self, wifi_list: list[dict], saved: set[str], empty_text: str) -> None:
        self._clear()

        if not wifi_list:
            self._show_empty_state(empty_text)
            return

        for network in wifi_list:
            ssid = network.get("ssid")
            if not ssid:
                continue

            try:
                button = add_hover_cursor(
                    widget=WifiButton(
                        ap=network,
                        network_service=self.nm,
                        on_connect=self.on_connect,
                        on_disconnect=self.on_disconnect,
                        is_saved=ssid in saved,
                    )
                )
            except Exception as e:
                logger.error(f"Error creating button for {ssid}: {e}")
                continue

            self.rows[ssid] = button
            if network.get("active", False):
                self.active_container.add(button)
            else:
                self.available_container.add(button)

    def _clear(self) -> None:
        self.rows.clear()
        for container in [self.active_container, self.available_container]:
            for child in container.get_children():
                child.destroy()

    def _show_empty_state(self, text: str) -> None:
        self.available_container.add(menu_placeholder(text))


class Network(TileSimpleWithMenu):
    STATUS_LABELS: ClassVar = {
        DeviceStatus.UNKNOWN: "Unavailable",
        DeviceStatus.DEVICE_OFF: "Off",
        DeviceStatus.DISCONNECTED: "Disconnected",
        DeviceStatus.CONNECTING: "Connecting…",
        DeviceStatus.DISCONNECTING: "Disconnecting…",
        DeviceStatus.FAILED: "Connection failed",
        DeviceStatus.NO_DEVICE: "No Device",
    }

    CONNECTION_FAILURES: ClassVar = {
        ConnectionResult.INVALID_PASSWORD: "Incorrect password",
        ConnectionResult.TIMEOUT: "Connection timed out",
        ConnectionResult.NETWORK_NOT_FOUND: "Network not found",
        ConnectionResult.NO_DEVICE: "No Wi-Fi adapter",
    }

    CONN_TYPE_META: ClassVar = {
        ConnectionType.WIFI: {"text": "Wi-Fi", "icon": icons.material.wifi.symbol()},
        ConnectionType.ETHERNET: {
            "text": "Ethernet",
            "icon": icons.material.lan.symbol(),
        },
        ConnectionType.NONE: {
            "text": "Internet",
            "icon": icons.material.globe_2_question.symbol(),
        },
    }

    def __init__(self, **kwargs):
        self.state: bool | None = None
        self._is_initialized = False

        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
        )

        self.nm = NetworkService()
        self.nm.connect("primary-connection-change", self._on_connection_change)
        self.nm.connect("ethernet-change", self._on_ethernet_list_changed)

        self.nm.connect("notify::wifi-enabled", self._on_wifi_radio_change)
        self.nm.connect("notify::wifi-hardware-enabled", self._on_wifi_radio_change)

        self.wifi_dev = self.nm.get_wifi_device()
        if self.wifi_dev:
            self.wifi_dev.connect("ap-change", self._on_ap_list_change)
            self.wifi_dev.connect("connection-result", self._on_connection_result)
            self.wifi_dev.connect("scan-state-change", self._on_scan_state_change)
            self.wifi_dev.connect("state-changed", self._on_wifi_state_change)

        self._primary_device_singal_id = None
        self._primary_device = None

        # the ssid we asked NM to connect to, until it reports back
        self._connect_target: str | None = None
        self._connect_failures: dict[str, str] = {}
        self._wifi_rescan_pending = False
        self._wifi_rescan_min_elapsed = False
        self._ethernet_refresh_pending = False
        self._wifi_radio_was_on = self.nm.wifi_enabled and self.nm.wifi_hardware_enabled
        # set while a radio that just turned on waits for its adapter to come up
        self._radio_ready_timeout_id: int | None = None
        self._wifi_list_signature: tuple | None = None

        self.menu_loader = TileMenuLoader()

        self.wifi_toggle = Gtk.Switch(name="matugen-switcher")
        self.wifi_toggle.set_active(self.nm.wifi_enabled)
        self.wifi_handler_id = self.wifi_toggle.connect(
            "notify::active", self._do_toggle_wifi
        )
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

        # ethernet
        self.ethernet_connection_container = Box(
            name="connection-container", orientation="v", spacing=2, children=[]
        )
        self.ethernet_scrolled_container = ClippingBox(
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
                child=self.ethernet_connection_container,
            ),
        )

        self.wifi_fader = ContentFader(self.active_connection, self.scrolled_container)
        self.ethernet_fader = ContentFader(self.ethernet_scrolled_container)

        self.ethernet_rescan_button = self._build_rescan_button(
            self._refresh_ethernet, "Refresh"
        )
        self.wifi_rescan_button = self._build_rescan_button(self._rescan_wifi, "Rescan")

        self.menu = self._build_menu()
        self.menu.connect("map", lambda *_: self.register_keybindings())
        self.menu.connect("unmap", lambda *_: self.unregister_keybindings())

        self.list_manager = NetworkListManager(
            self.active_connection,
            self.connection_container,
            self.nm.get_wifi_device(),
            self._handle_network_connect,
            self._disconnect_wifi,
        )

        self.password_dialog: PasswordDialog | None = None

        super().__init__(
            title="Internet",
            label="Wi-Fi",
            status_label_widget=self.label,
            markup=icons.material.wifi.symbol(),
            menu_children=self.menu,
            menu_loader=self.menu_loader,
            style_classes=["off"],
            **kwargs,
        )

        self.reveal_status_widget()
        self._initialize_network_state()

    @staticmethod
    def _build_rescan_button(on_clicked: Callable[[], None], tooltip: str) -> Button:
        return add_hover_cursor(
            Button(
                h_align="end",
                style_classes=["menu-icon-btn"],
                on_clicked=lambda *_: on_clicked(),
                child=MaterialIconLabel(
                    style_classes=["menu-icon"],
                    icon_text=icons.material.refresh.symbol(),
                ),
                tooltip_markup=tooltip,
            )
        )

    def _build_menu(self) -> Box:
        return Box(
            name="network-menu",
            orientation="v",
            spacing=10,
            children=[
                # ethernet
                Box(
                    name="subsection-heading-container",
                    h_expand=True,
                    v_expand=True,
                    children=[
                        Label(
                            name="subsection-heading-label",
                            label="Ethernet",
                            h_expand=True,
                            justification="left",
                            h_align="start",
                        ),
                        self.ethernet_rescan_button,
                    ],
                ),
                self.ethernet_scrolled_container,
                # wifi
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
                        self.wifi_rescan_button,
                    ],
                ),
                self.scrolled_container,
            ],
        )

    def _keybindings(self):
        wifi_bindings = config.get("bindings.modules.wifi")
        return {
            format_accel_to_keybind(wifi_bindings["wifi.rescan"]): self._rescan_wifi,
        }

    def register_keybindings(self):
        window = self.get_toplevel()
        for key, handler in self._keybindings().items():
            window.add_keybinding(key, lambda *_, h=handler: h())

    def unregister_keybindings(self):
        window = self.get_toplevel()
        for key in self._keybindings():
            window.remove_keybinding(key)

    def _initialize_network_state(self) -> None:
        try:
            self._populate_ethernet()
            if self.wifi_dev:
                # also runs the initial wifi list update through _on_ap_list_change
                self.wifi_dev.refresh_access_points()
            else:
                self._refresh_wifi_list(force=True)
            self._sync_wifi_controls()
            self._sync_tile()
            self._sync_loader()
            self._is_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize network state: {e}")

    def _on_ethernet_list_changed(self):
        if not self._ethernet_refresh_pending:
            self.ethernet_fader.swap(self._populate_ethernet)

    def _populate_ethernet(self) -> None:
        container = self.ethernet_connection_container
        for child in container.get_children():
            container.remove(child)
            child.destroy()

        eth_list = [
            eth_info
            for eth_info in self.nm.get_ethernet_list()
            if eth_info.get("device") is not None
        ]
        if not eth_list:
            container.add(menu_placeholder("No Ethernet adapters"))

        for eth_info in eth_list:
            container.add(
                add_hover_cursor(
                    widget=EthernetButton(
                        eth_conn=eth_info,
                        network_service=self.nm,
                        on_state_change=self._sync_loader,
                    )
                )
            )

    def _refresh_ethernet(self) -> None:
        # the list is always current, but the user asked for a visible refresh
        if self._ethernet_refresh_pending:
            return

        self._ethernet_refresh_pending = True
        self.ethernet_rescan_button.set_sensitive(False)
        self.ethernet_fader.dim()
        self._sync_loader()
        GLib.timeout_add(MIN_BUSY_MS, self._finish_ethernet_refresh)

    def _finish_ethernet_refresh(self) -> bool:
        self._ethernet_refresh_pending = False
        self.ethernet_rescan_button.set_sensitive(True)
        self.ethernet_fader.swap(self._populate_ethernet)
        self._sync_loader()
        return False

    def _rescan_wifi(self) -> None:
        if self.wifi_dev is None:
            logger.error("[Network] Wifi device is None, couldn't request scan.")
            return

        if self._wifi_rescan_pending or not self.nm.wifi_enabled:
            return

        self._wifi_rescan_pending = True
        self._wifi_rescan_min_elapsed = False
        self.wifi_fader.dim()
        self._sync_wifi_controls()
        self._sync_loader()

        # False means a scan is already running, so its results are good enough
        self.wifi_dev.scan()
        GLib.timeout_add(MIN_BUSY_MS, self._on_rescan_min_elapsed)

    def _on_rescan_min_elapsed(self) -> bool:
        self._wifi_rescan_min_elapsed = True
        self._maybe_finish_rescan()
        return False

    def _maybe_finish_rescan(self) -> None:
        if (
            not self._wifi_rescan_pending
            or not self._wifi_rescan_min_elapsed
            or self.wifi_dev.scanning
        ):
            return

        self._wifi_rescan_pending = False
        self._refresh_wifi_list(force=True)
        self._sync_wifi_controls()
        self._sync_loader()

    def _on_scan_state_change(self, source: WifiDevice, scanning: bool) -> None:
        self._sync_wifi_controls()
        self._sync_loader()
        self._maybe_finish_rescan()

    def _sync_loader(self) -> None:
        wifi_connecting = self._connect_target is not None or (
            self.wifi_dev is not None
            and self.wifi_dev.state
            in (DeviceStatus.CONNECTING, DeviceStatus.DISCONNECTING)
        )
        scanning = (
            self._wifi_rescan_pending
            or self._radio_ready_timeout_id is not None
            or (self.wifi_dev is not None and self.wifi_dev.scanning)
        )
        ethernet_busy = self._ethernet_refresh_pending or any(
            eth_info["state"] in (DeviceStatus.CONNECTING, DeviceStatus.DISCONNECTING)
            for eth_info in self.nm.get_ethernet_list()
        )

        self.menu_loader.set_busy("wifi-scan", scanning)
        self.menu_loader.set_busy("wifi-connection", wifi_connecting)
        self.menu_loader.set_busy("ethernet", ethernet_busy)

    def _sync_wifi_controls(self) -> None:
        has_device = self.wifi_dev is not None
        radio_on = self.nm.wifi_enabled
        hardware_on = self.nm.wifi_hardware_enabled

        self.wifi_toggle.set_sensitive(has_device and hardware_on)
        if not has_device:
            self.wifi_toggle.set_tooltip_text("No Wi-Fi adapter")
        elif not hardware_on:
            self.wifi_toggle.set_tooltip_text("Blocked by a hardware switch")
        else:
            self.wifi_toggle.set_tooltip_text(None)

        # programmatic change, prevent callback
        self.wifi_toggle.handler_block(self.wifi_handler_id)
        self.wifi_toggle.set_active(radio_on)
        self.wifi_toggle.handler_unblock(self.wifi_handler_id)

        self.wifi_rescan_button.set_sensitive(
            has_device
            and radio_on
            and not self._wifi_rescan_pending
            and self._radio_ready_timeout_id is None
            and not self.wifi_dev.scanning
        )

    def _on_wifi_radio_change(self, *_) -> None:
        radio_on = self.nm.wifi_enabled and self.nm.wifi_hardware_enabled
        turned_on = radio_on and not self._wifi_radio_was_on
        self._wifi_radio_was_on = radio_on

        if not radio_on:
            self._stop_waiting_for_radio()
        elif turned_on and self.wifi_dev is not None:
            self._radio_ready_timeout_id = GLib.timeout_add_seconds(
                NetworkConstants.SCAN_TIMEOUT_SECONDS, self._on_radio_ready_timeout
            )

        self._sync_wifi_controls()
        self._sync_loader()
        self._refresh_wifi_list()
        # NM doesn't order this against the device's state change, it may be up
        self._scan_if_radio_ready()

    def _stop_waiting_for_radio(self) -> None:
        if self._radio_ready_timeout_id is not None:
            GLib.source_remove(self._radio_ready_timeout_id)
            self._radio_ready_timeout_id = None

    def _scan_if_radio_ready(self) -> None:
        # NM rejects scans until the adapter has left the "unavailable" state
        if self._radio_ready_timeout_id is None or self.wifi_dev.state in (
            DeviceStatus.DEVICE_OFF,
            DeviceStatus.UNKNOWN,
        ):
            return

        self._stop_waiting_for_radio()
        self._rescan_wifi()

    def _on_radio_ready_timeout(self) -> bool:
        logger.warning("[Network] Wi-Fi adapter didn't come up, skipping the scan")
        self._radio_ready_timeout_id = None
        self._sync_wifi_controls()
        self._sync_loader()
        self._refresh_wifi_list()
        return False

    def _wifi_empty_text(self) -> str:
        if self.wifi_dev is None:
            return "No Wi-Fi adapter"
        if not self.nm.wifi_hardware_enabled:
            return "Wi-Fi is blocked by a hardware switch"
        if not self.nm.wifi_enabled:
            return "Wi-Fi is off"
        if (
            self.wifi_dev.scanning
            or self._wifi_rescan_pending
            or self._radio_ready_timeout_id is not None
        ):
            return "Searching for networks…"
        return "No networks found"

    def _refresh_wifi_list(self, force: bool = False) -> None:
        radio_on = self.nm.wifi_enabled and self.wifi_dev is not None
        wifi_list = self.wifi_dev.get_networks() if radio_on else []
        saved = set(self.wifi_dev.get_saved_networks()) if self.wifi_dev else set()
        empty_text = self._wifi_empty_text()

        signature = self.list_manager.make_signature(wifi_list, saved, empty_text)
        if not force and signature == self._wifi_list_signature:
            self._apply_wifi_row_states()
            return

        # compare against what was last asked for: a swap may still be fading out
        self._wifi_list_signature = signature

        def populate():
            self.list_manager.update(wifi_list, saved, empty_text)
            self._apply_wifi_row_states()

        self.wifi_fader.swap(populate)

    def _apply_wifi_row_states(self) -> None:
        if self.wifi_dev is None:
            return

        status = self.wifi_dev.state
        active_ssid = self.wifi_dev.active_ssid
        detail = self.wifi_dev.status_detail

        for ssid, row in self.list_manager.rows.items():
            if ssid == active_ssid and status == DeviceStatus.CONNECTED:
                row.set_row_state(WifiRowState.CONNECTED, "Connected")
            elif ssid == active_ssid and status == DeviceStatus.DISCONNECTING:
                row.set_row_state(WifiRowState.DISCONNECTING, detail)
            elif ssid == active_ssid and status == DeviceStatus.CONNECTING:
                row.set_row_state(WifiRowState.CONNECTING, detail)
            elif ssid == self._connect_target:
                row.set_row_state(WifiRowState.CONNECTING, "Connecting…")
            elif ssid in self._connect_failures:
                row.set_row_state(WifiRowState.FAILED, self._connect_failures[ssid])
            else:
                row.set_row_state(WifiRowState.IDLE)

    def _on_wifi_state_change(self, source, ssid: str, status: DeviceStatus) -> None:
        self._apply_wifi_row_states()
        self._sync_tile()
        self._sync_loader()
        self._scan_if_radio_ready()

    def _show_connect_failure(self, ssid: str, text: str) -> None:
        self._connect_failures[ssid] = text

        def clear() -> bool:
            if self._connect_failures.get(ssid) == text:
                del self._connect_failures[ssid]
                self._apply_wifi_row_states()
            return False

        GLib.timeout_add(UIConstants.FAILURE_DISPLAY_MS, clear)

    def _disconnect_wifi(self) -> None:
        self._connect_target = None
        if self.wifi_dev is None or not self.wifi_dev.disconnect_network():
            logger.warning("Failed to disconnect")
        self._apply_wifi_row_states()
        self._sync_loader()

    def _do_toggle_wifi(self, switch: Gtk.Switch, pspec: Any) -> None:
        if not self._is_initialized:
            return

        enabled = switch.get_active()

        try:
            success = self.nm.toggle_wifi_radio(enabled=enabled)

            if not success:
                # revert toggle
                # programmatic change, prevent callback
                self.wifi_toggle.handler_block(self.wifi_handler_id)
                switch.set_active(not enabled)
                self.wifi_toggle.handler_unblock(self.wifi_handler_id)

                logger.error("Failed to toggle WiFi radio")
                return

            # Save last successful state preferred by user
            # (Note: NetworkManager already restores WiFi state after sleep.)
            config.set("network.wifi.enabled", enabled)

        except Exception as e:
            logger.error(f"Error toggling WiFi: {e}")
            # programmatic change, prevent callback
            self.wifi_toggle.handler_block(self.wifi_handler_id)
            switch.set_active(not enabled)
            self.wifi_toggle.handler_unblock(self.wifi_handler_id)

    def _on_ap_list_change(self, source: WifiDevice) -> None:
        # a pending rescan shows the final list in one go when it finishes
        if self._wifi_rescan_pending:
            return

        try:
            self._refresh_wifi_list()
        except Exception as e:
            logger.error(f"Error updating access point list: {e}")

    def _on_connection_change(
        self, source: NetworkService, device: EthernetDevice | WifiDevice | None
    ) -> None:

        # wire up new device
        if (
            self._primary_device_singal_id is not None
            and self._primary_device is not None
        ):
            self._primary_device.disconnect(self._primary_device_singal_id)

        self._primary_device_singal_id = None
        self._primary_device = device
        if device is not None:
            self._primary_device_singal_id = device.connect(
                "state-changed", lambda *_: self._sync_tile()
            )
            logger.info(f"Updating primary connection -> status: {device.state}")

        self._sync_tile()

    def _sync_tile(self) -> None:
        device = self._primary_device
        if device is None or device.state != DeviceStatus.CONNECTED:
            # nothing's up, the wifi device has the more interesting story to tell
            device = self.wifi_dev or device

        if device is None:
            self._update_visuals("", DeviceStatus.NO_DEVICE, ConnectionType.NONE)
            return

        conn_type = device.CONNECTION_TYPE
        if conn_type == ConnectionType.WIFI:
            name = device.active_ssid
        else:
            name = EthernetDevice._ethernet_display_name(device)

        self._update_visuals(name, device.state, conn_type)

    def _update_visuals(
        self, name: str, status: DeviceStatus, conn_type: ConnectionType
    ):
        is_connected = status == DeviceStatus.CONNECTED

        self.add_style_class("on" if is_connected else "off")
        self.remove_style_class("off" if is_connected else "on")

        label_text = name if is_connected else self.STATUS_LABELS.get(status, "Unknown")
        self.label.set_label(label_text or "Connected")

        meta = self.CONN_TYPE_META.get(
            conn_type, self.CONN_TYPE_META[ConnectionType.NONE]
        )
        self.tile_label.set_label(meta["text"])
        self.icon.set_icon(meta["icon"])

    def _on_connection_result(
        self, source: NetworkService, ssid: str, result: ConnectionResult, message: str
    ) -> None:
        if self._connect_target == ssid:
            self._connect_target = None

        if result == ConnectionResult.INVALID_PASSWORD:
            self._show_connect_failure(
                ssid, self.CONNECTION_FAILURES[ConnectionResult.INVALID_PASSWORD]
            )
            self._show_password_dialog(ssid, "Incorrect password. Please try again.")

        elif result == ConnectionResult.SUCCESS:
            logger.info(f"Successfully connected to {ssid}")
            BaseDialog.show_notification(f"Connected to {ssid}")

            if self.password_dialog:
                self.password_dialog.destroy()
                self.password_dialog = None

        else:
            self._show_connect_failure(
                ssid, self.CONNECTION_FAILURES.get(result, "Couldn't connect")
            )

        self._apply_wifi_row_states()
        self._sync_loader()

    def _handle_network_connect(self, ssid: str, password: str | None = None) -> None:
        try:
            result = self.nm.get_wifi_device().connect_to_network(ssid, password)

            if result == ConnectionResult.PASSWORD_REQUIRED:
                self._show_password_dialog(ssid)

            elif result == ConnectionResult.ALREADY_CONNECTED:
                logger.info(f"Already connected to {ssid}")

            elif result == ConnectionResult.NETWORK_NOT_FOUND:
                self._show_connect_failure(ssid, self.CONNECTION_FAILURES[result])
                BaseDialog.show_notification(f"Network '{ssid}' not found")

            elif result == ConnectionResult.NO_DEVICE:
                BaseDialog.show_notification("No WiFi device available")

            elif result == ConnectionResult.CONNECTION_FAILED:
                self._show_connect_failure(ssid, "Couldn't connect")
                BaseDialog.show_notification(f"Failed to connect to '{ssid}'")

            elif result == ConnectionResult.SUCCESS:
                self._connect_target = ssid
                self._connect_failures.pop(ssid, None)
                BaseDialog.show_notification(f"Connecting to {ssid}...")

            self._apply_wifi_row_states()
            self._sync_loader()

        except Exception as e:
            logger.error(f"Error handling network connection: {e}")
            BaseDialog.show_notification("Connection error occurred")

    def _show_password_dialog(
        self, ssid: str, error_message: str | None = None
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
