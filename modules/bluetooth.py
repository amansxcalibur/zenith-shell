from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.bluetooth import BluetoothClient, BluetoothDevice

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from widgets.tile_menu import (
    MIN_BUSY_MS,
    ContentFader,
    TileMenuLoader,
    menu_placeholder,
)

import icons
from modules.tile import Tile
from config.config import config
from utils.cursor import add_hover_cursor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # type: ignore

WINDOW_MAX_WIDTH = 250
WINDOW_MAX_HEIGHT = 270
MAX_SSID_DISPLAY_LENGTH = 8
DIALOG_DEFAULT_WIDTH = 350
UPDATE_DIALOG_WIDTH = 350
MAX_DEVICE_NAME_CHARS = 20
FAILURE_DISPLAY_MS = 5000
POWER_CHANGE_TIMEOUT_MS = 5000


class Bluetooth(Tile):
    def __init__(self, **kwargs):
        self.client = BluetoothClient()
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
        )

        loader = TileMenuLoader()
        self.bluetooth_connections = BluetoothConnections(loader=loader)

        super().__init__(
            label="Bluetooth",
            props=self.label,
            markup=icons.bluetooth.symbol(),
            menu_children=self.bluetooth_connections,
            menu_loader=loader,
            style_classes=["off"],
            on_toggle=self._on_tile_toggled,
            **kwargs,
        )

        self.client.connect("changed", self.update_tile)
        self.update_tile()

    def _on_tile_toggled(self):
        self.bluetooth_connections.set_enabled(self.state)
        # with an adapter, the update comes through "changed" once it has settled
        if self.client.state == "absent":
            self.update_tile()

    def update_tile(self, *args):
        # the adapter can also be toggled from the menu or from outside the shell
        self.state = self.client.enabled

        if not self.client.enabled:
            self.remove_style_class("on")
            self.add_style_class("off")
            self.label.set_label(
                "No adapter" if self.client.state == "absent" else "Off"
            )
            return

        self.remove_style_class("off")

        conns = self.client.connected_devices
        if len(conns) > 0:
            self.reveal_status_widget()
            self.label.set_label(
                conns[0].name if len(conns) == 1 else f"{len(conns)} Connected"
            )
            self.add_style_class("on")
        else:
            self.label.set_label("On")
            self.hide_status_widget()
            self.add_style_class("on")


class BluetoothDeviceSlot(CenterBox):
    def __init__(
        self,
        device: BluetoothDevice,
        on_state_change: Callable[["BluetoothDeviceSlot"], None] = lambda _: None,
        on_paired_change: Callable[[], None] = lambda: None,
        **kwargs,
    ):
        super().__init__(name="bluetooth-device-btn", **kwargs)
        self.device = device
        self.on_state_change = on_state_change
        self.on_paired_change = on_paired_change

        self._adapter_on = True
        self._was_paired = device.paired
        self._was_connecting = device.connecting
        self._attempted_connect = False
        self._failed = False
        self._failure_timer: int | None = None

        # slots get rebuilt, the device outlives them
        handlers = [
            self.device.connect("changed", self.on_changed),
            self.device.connect("notify::closed", lambda *_: self.destroy()),
        ]
        self.connect("destroy", lambda *_: self._on_destroyed(handlers))

        self.connection_label = Label(name="bt-dev-connection-label", h_align="start")

        self.connect_button = add_hover_cursor(
            Button(
                name="bt-connect-btn",
                on_clicked=lambda *_: self._toggle_connection(),
            )
        )

        # self.forget_button = Button(
        #     label="Forget",
        #     visible=self.device.paired,
        #     on_clicked=self.on_forget_clicked,
        # )

        icon_name = (device.icon_name or "bluetooth") + "-symbolic"
        self.start_children = Box(
            spacing=10,
            children=[
                Box(
                    name="bluetooth-device-img",
                    children=Image(icon_name=icon_name, size=32),
                ),
                Box(
                    orientation="vertical",
                    v_align="center",
                    children=[
                        Label(
                            label=device.alias or device.name or device.address,
                            h_align="start",
                            max_chars_width=MAX_DEVICE_NAME_CHARS,
                            ellipsization="end",
                        ),
                        self.connection_label,
                    ],
                ),
            ],
        )
        self.end_children = Box(
            spacing=10,
            children=[
                self.connect_button,
                # self.forget_button
            ],
        )

        self.on_changed()

    def _on_destroyed(self, handlers: list[int]):
        self._clear_failure_timer()
        for handler in handlers:
            self.device.disconnect(handler)

    def _clear_failure_timer(self):
        if self._failure_timer is not None:
            GLib.source_remove(self._failure_timer)
            self._failure_timer = None

    def on_forget_clicked(self, *args):
        # TODO
        ...

    def set_adapter_on(self, adapter_on: bool):
        self._adapter_on = adapter_on
        self._update_ui()

    def _toggle_connection(self):
        self._attempted_connect = not self.device.connected
        self._set_failed(False)
        self.device.set_property("connecting", self._attempted_connect)
        # the service doesn't notify when an attempt starts, only when it ends
        self.on_changed()

    def _set_failed(self, failed: bool):
        self._clear_failure_timer()
        self._failed = failed
        if failed:
            self._failure_timer = GLib.timeout_add(
                FAILURE_DISPLAY_MS, self._on_failure_expired
            )

    def _on_failure_expired(self) -> bool:
        self._failure_timer = None
        self._failed = False
        self._update_ui()
        return False

    def on_changed(self, *_):
        connecting = self.device.connecting

        if self._was_connecting and not connecting:
            self._set_failed(self._attempted_connect and not self.device.connected)
        elif self.device.connected:
            self._set_failed(False)
        self._was_connecting = connecting

        self._update_ui()
        self.on_state_change(self)

        if self.device.paired != self._was_paired:
            self._was_paired = self.device.paired
            self.on_paired_change()

    def _status_text(self) -> str:
        if self.device.connecting:
            return "Disconnecting…" if self.device.connected else "Connecting…"
        if self.device.connected:
            battery = self.device.battery_percentage
            return f"Connected · {battery:.0f}%" if battery > 0 else "Connected"
        if self._failed:
            return "Couldn't connect"
        return "Not connected" if self.device.paired else "Available"

    def _update_ui(self):
        connected = self.device.connected
        connecting = self.device.connecting

        self.connection_label.set_label(self._status_text())
        # self.forget_button.set_visible(self.device.paired)

        self.connect_button.set_label("Disconnect" if connected else "Connect")
        self.connect_button.set_sensitive(self._adapter_on and not connecting)


class BluetoothConnections(Box):
    def __init__(self, loader: TileMenuLoader, **kwargs):
        super().__init__(
            name="network-menu",
            spacing=4,
            orientation="vertical",
            **kwargs,
        )

        self.loader = loader
        self._refresh_pending = False
        # what the user asked the adapter to become, until it gets there
        self._power_target: bool | None = None
        self._power_timeout_id: int | None = None

        self.client = BluetoothClient()

        self.scan_icon = MaterialIconLabel(
            name="scan-icon", icon_text=icons.radar.symbol()
        )
        self.scan_label = Label(name="scan-label", label="")
        self.scan_label_revealer = Revealer(
            child=self.scan_label,
            transition_duration=300,
            child_revealed=False,
            transition_type="slide-left",
        )
        self.scan_button = add_hover_cursor(
            Button(
                name="bluetooth-scan-btn",
                child=Box(
                    spacing=4, children=[self.scan_label_revealer, self.scan_icon]
                ),
                on_clicked=lambda *_: self.client.toggle_scan(),
            )
        )

        self.scan_button.connect(
            "enter-notify-event", lambda *_: self.scan_label_revealer.reveal()
        )
        self.scan_button.connect(
            "leave-notify-event", lambda *_: self.scan_label_revealer.unreveal()
        )

        self.refresh_icon = MaterialIconLabel(
            name="scan-icon", icon_text=icons.refresh.symbol()
        )
        self.refresh_button = add_hover_cursor(
            widget=Button(
                # name="bluetooth-scan-btn",
                style_classes=["menu-icon-btn"],
                child=Box(spacing=4, children=[self.refresh_icon]),
                on_clicked=lambda *_: self.refresh_list(),
                tooltip_markup="Refresh list",
            )
        )

        self.bluetooth_toggle = Gtk.Switch(name="matugen-switcher")
        self.bluetooth_handler_id = self.bluetooth_toggle.connect(
            "notify::active", self.on_switch_toggled
        )
        self.bluetooth_toggle.set_visible(True)
        self.bluetooth_toggle.set_active(config.get("bluetooth.enabled"))

        self.paired_box = ClippingBox(
            name="network-scrolled-window-container",
            orientation="v",
            spacing=2,
        )
        self.available_box = ClippingBox(
            name="network-scrolled-window-container",
            orientation="v",
            spacing=2,
        )

        self.paired_window = ScrolledWindow(
            name="network-scrolled-window",
            h_expand=True,
            max_content_size=(
                WINDOW_MAX_WIDTH,
                WINDOW_MAX_HEIGHT,
            ),
            h_scrollbar_policy="external",
            v_scrollbar_policy="external",
            child=self.paired_box,
        )
        self.available_window = ScrolledWindow(
            name="network-scrolled-window",
            h_expand=True,
            max_content_size=(
                WINDOW_MAX_WIDTH,
                WINDOW_MAX_HEIGHT,
            ),
            h_scrollbar_policy="external",
            v_scrollbar_policy="external",
            child=self.available_box,
        )
        self.list_fader = ContentFader(self.paired_window, self.available_window)

        self.children = [
            CenterBox(
                name="subsection-heading-container",
                start_children=Label(
                    label="Bluetooth", name="subsection-heading-label"
                ),
                end_children=[self.bluetooth_toggle],
            ),
            CenterBox(
                name="subsection-heading-container",
                start_children=Label(label="Paired Devices"),
                end_children=self.refresh_button,
            ),
            self.paired_window,
            CenterBox(
                name="subsection-heading-container",
                start_children=Label(label="Available Devices"),
                end_children=self.scan_button,
            ),
            self.available_window,
        ]

        self._populate_list()

        self.client.connect("device-added", self.on_device_added)
        # a removed device closes (and destroys its slot) right after this signal
        self.client.connect(
            "device-removed",
            lambda *_: GLib.idle_add(self._after_device_removed),
        )
        self.client.connect("notify::enabled", self._sync_controls)
        self.client.connect("notify::state", self._sync_controls)
        self.client.connect("notify::scanning", self._sync_controls)

        self._sync_controls()

    def _slots(self) -> list[BluetoothDeviceSlot]:
        return [
            child
            for box in (self.paired_box, self.available_box)
            for child in box.get_children()
            if isinstance(child, BluetoothDeviceSlot)
        ]

    def _make_slot(self, device: BluetoothDevice) -> BluetoothDeviceSlot:
        slot = BluetoothDeviceSlot(
            device,
            on_state_change=lambda _slot: self._sync_connection_loader(),
            on_paired_change=lambda: self.list_fader.swap(self._populate_list),
        )
        slot.set_adapter_on(self.client.state == "on")
        return slot

    def on_device_added(self, client: BluetoothClient, address: str):
        if not (device := client.get_device(address)):
            return

        slot = self._make_slot(device)
        (self.paired_box if device.paired else self.available_box).add(slot)
        self._sync_placeholders()

        slot._fader = ContentFader(slot)
        slot._fader.fade_in()

    def _after_device_removed(self) -> bool:
        self._sync_placeholders()
        self._sync_connection_loader()
        return False

    def set_enabled(self, state: bool):
        if self.client.enabled != state:
            # set first: toggling notifies right away, with the old state
            self._power_target = state
            self._power_timeout_id = GLib.timeout_add(
                POWER_CHANGE_TIMEOUT_MS, self._on_power_change_timeout
            )
            self.client.toggle_power()
            config.set("bluetooth.enabled", state)

    def _on_power_change_timeout(self) -> bool:
        # eg: blocked by rfkill, show what the adapter is actually doing
        self._power_timeout_id = None
        self._power_target = None
        self._sync_controls()
        return False

    def _settle_power_target(self, state: str) -> None:
        if self._power_target is None or state != (
            "on" if self._power_target else "off"
        ):
            return

        self._power_target = None
        GLib.source_remove(self._power_timeout_id)
        self._power_timeout_id = None

    def on_switch_toggled(self, switch, pspec):
        self.set_enabled(switch.get_active())

    def refresh_list(self):
        if self._refresh_pending:
            return

        self._refresh_pending = True
        self.list_fader.dim()
        self.loader.set_busy("bt-refresh", True)
        self._sync_controls()
        # rebuilding is instant, keep the loader up long enough to be seen
        GLib.timeout_add(MIN_BUSY_MS, self._finish_refresh)

    def _finish_refresh(self) -> bool:
        self._refresh_pending = False
        self.list_fader.swap(self._populate_list)
        self.loader.set_busy("bt-refresh", False)
        self._sync_controls()
        return False

    def _populate_list(self):
        for box in (self.paired_box, self.available_box):
            for child in box.get_children():
                child.destroy()

        devices = sorted(
            self.client.devices,
            key=lambda device: (
                not device.connected,
                (device.alias or device.name or "").lower(),
            ),
        )
        for device in devices:
            box = self.paired_box if device.paired else self.available_box
            box.add(self._make_slot(device))

        self._sync_placeholders()
        self._sync_connection_loader()

    def _sync_placeholders(self):
        state = self.client.state
        if state == "absent":
            paired_text = available_text = "No Bluetooth adapter"
        elif state != "on":
            paired_text = "No paired devices"
            available_text = "Turn on Bluetooth to find devices"
        else:
            paired_text = "No paired devices"
            available_text = (
                "Searching for devices…"
                if self.client.scanning
                else "Start a scan to find devices"
            )

        for box, text in (
            (self.paired_box, paired_text),
            (self.available_box, available_text),
        ):
            children = box.get_children()
            has_slots = any(isinstance(c, BluetoothDeviceSlot) for c in children)
            for child in children:
                if not isinstance(child, BluetoothDeviceSlot):
                    child.destroy()
            if not has_slots:
                box.add(menu_placeholder(text))

    def _sync_connection_loader(self):
        self.loader.set_busy(
            "bt-connection", any(slot.device.connecting for slot in self._slots())
        )

    def _sync_controls(self, *_):
        state = self.client.state
        adapter_on = state == "on"

        self._settle_power_target(state)
        power_changing = self._power_target is not None
        if power_changing:
            switch_active = self._power_target
        else:
            switch_active = state in ("on", "turning-on")

        # programmatic change, prevent callback
        self.bluetooth_toggle.handler_block(self.bluetooth_handler_id)
        self.bluetooth_toggle.set_active(switch_active)
        self.bluetooth_toggle.handler_unblock(self.bluetooth_handler_id)
        # powering up or down takes a moment, wait for it to settle
        self.bluetooth_toggle.set_sensitive(
            state in ("on", "off") and not power_changing
        )

        scanning = adapter_on and self.client.scanning
        self.scan_button.set_sensitive(adapter_on)
        self.refresh_button.set_sensitive(adapter_on and not self._refresh_pending)

        for slot in self._slots():
            slot.set_adapter_on(adapter_on)

        self.scan_label.set_label("Stop" if scanning else "Scan")
        if scanning:
            self.scan_icon.add_style_class("bt-scanning")
        else:
            self.scan_icon.remove_style_class("bt-scanning")

        self.loader.set_busy(
            "bt-power", power_changing or state in ("turning-on", "turning-off")
        )
        self.loader.set_busy("bt-scan", scanning)

        self._sync_placeholders()
