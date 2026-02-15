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

import icons
from modules.tile import Tile
from config.config import config
from utils.cursor import add_hover_cursor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

WINDOW_MAX_WIDTH = 250
WINDOW_MAX_HEIGHT = 250
MAX_SSID_DISPLAY_LENGTH = 8
DIALOG_DEFAULT_WIDTH = 350
UPDATE_DIALOG_WIDTH = 350


class Bluetooth(Tile):
    def __init__(self, **kwargs):
        self.client = BluetoothClient()
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
            ellipsization="end",
            max_chars_width=9,
        )

        super().__init__(
            label="Bluetooth",
            props=self.label,
            markup=icons.bluetooth.symbol(),
            menu=True,
            menu_children=BluetoothConnections(),
            style_classes=["off"],
            **kwargs,
        )

        self.client.connect("changed", self.update_tile)
        self.update_tile()

    def update_tile(self, *args):
        if not self.client.enabled:
            self.remove_style_class("on")
            self.add_style_class("off")
            self.label.set_label("Off")
            return

        self.remove_style_class("off")

        conns = self.client.connected_devices
        if len(conns) > 0:
            self.label.set_label(
                conns[0].name if len(conns) == 1 else f"{len(conns)} Connected"
            )
            self.add_style_class("on")
        else:
            self.label.set_label("On")
            self.add_style_class("on")


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(name="bluetooth-device-btn", **kwargs)
        self.device = device
        self.device.connect("changed", self.on_changed)
        self.device.connect("notify::closed", lambda *_: self.destroy())

        self.connection_label = Label(
            name="bt-dev-connection-label", label="Disconnected"
        )

        self.connect_button = Button(
            name="bt-connect-btn",
            label="Connect",
            on_clicked=lambda *_: self.device.set_property(
                "connecting", not self.device.connected
            ),
        )

        # self.forget_button = Button(
        #     label="Forget",
        #     visible=self.device.paired,
        #     on_clicked=self.on_forget_clicked,
        # )

        self.start_children = Box(
            spacing=10,
            children=[
                Box(
                    name="bluetooth-device-img",
                    children=Image(icon_name=device.icon_name + "-symbolic", size=32),
                ),
                Box(
                    orientation="vertical",
                    children=[
                        Label(label=device.name, h_align="start"),
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

    def on_forget_clicked(self, *args):
        # TODO
        ...

    def on_changed(self, *_):
        self.connection_label.set_label(
            "Connected" if self.device.connected else "Disconnected"
        )
        self.forget_button.set_visible(self.device.paired)

        if self.device.connecting:
            self.connect_button.set_label("...")
        else:
            self.connect_button.set_label(
                "Disconnect" if self.device.connected else "Connect"
            )


class BluetoothConnections(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="network-menu",
            spacing=4,
            orientation="vertical",
            **kwargs,
        )

        self.client = BluetoothClient(on_device_added=self.on_device_added)

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
        self.scan_button = Button(
            name="bluetooth-scan-btn",
            child=Box(spacing=4, children=[self.scan_label_revealer, self.scan_icon]),
            on_clicked=lambda *_: self.client.toggle_scan(),
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
                child=Box(spacing=4, children=[self.refresh_icon]),
                on_clicked=lambda *_: self.refresh_list(),
                tooltip_markup="Refresh list",
            )
        )

        self.bluetooth_toggle = Gtk.Switch(name="matugen-switcher")
        self._last_enabled = self.bluetooth_toggle.get_active()
        self.bluetooth_handler_id = self.bluetooth_toggle.connect(
            "notify::active", self.on_switch_toggled
        )
        self.bluetooth_toggle.set_visible(True)
        self.bluetooth_toggle.set_active(config.bluetooth.enabled)

        self.client.connect("notify::enabled", self._do_toggle_bluetooth)
        self.client.connect("notify::scanning", self.set_scan_ui)

        self.connected_box = ClippingBox(
            name="network-scrolled-window-container",
            orientation="v",
            spacing=2,
        )
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
            ScrolledWindow(
                name="network-scrolled-window",
                h_expand=True,
                max_content_size=(
                    WINDOW_MAX_WIDTH,
                    WINDOW_MAX_HEIGHT,
                ),
                h_scrollbar_policy="external",
                v_scrollbar_policy="external",
                child=self.paired_box,
            ),
            CenterBox(
                name="subsection-heading-container",
                start_children=Label(label="Available Devices"),
                end_children=self.scan_button,
            ),
            ScrolledWindow(
                name="network-scrolled-window",
                h_expand=True,
                max_content_size=(
                    WINDOW_MAX_WIDTH,
                    WINDOW_MAX_HEIGHT,
                ),
                h_scrollbar_policy="external",
                v_scrollbar_policy="external",
                child=self.available_box,
            ),
        ]

        # to run notify closures thus display the status
        # without having to wait until an actual change
        self.client.notify("scanning")
        self.client.notify("enabled")

        self.refresh_list()

    def on_device_added(self, client: BluetoothClient, address: str):
        if not (device := client.get_device(address)):
            return
        slot = BluetoothDeviceSlot(device)
        if device.paired:
            return self.paired_box.add(slot)
        return self.available_box.add(slot)
    
    def on_switch_toggled(self, switch, pspec):
        new_state = switch.get_active()
        if self.client.enabled != new_state:
            self.client.toggle_power()
            config.bluetooth.enabled = new_state

    def _do_toggle_bluetooth(self):
        # prevent callback
        enabled = self.client.enabled

        if enabled == self._last_enabled:
            return

        self._last_enabled = enabled
        self.bluetooth_toggle.handler_block(self.bluetooth_handler_id)
        self.bluetooth_toggle.set_active(enabled)
        self.bluetooth_toggle.handler_unblock(self.bluetooth_handler_id)

    def refresh_list(self):
        for box in [self.connected_box, self.paired_box, self.available_box]:
            for child in box.get_children():
                child.destroy()

        for device in self.client.devices:
            slot = BluetoothDeviceSlot(device)
            if device.paired:
                self.paired_box.add(slot)
            else:
                self.available_box.add(slot)

    def set_scan_ui(self):
        if self.client.scanning:
            self.scan_icon.add_style_class("bt-scanning")
            self.scan_label.set_label("Stop")
        else:
            self.scan_icon.remove_style_class("bt-scanning")
            self.scan_label.set_label("Scan")
