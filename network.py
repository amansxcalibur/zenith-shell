from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.button import Button
# from services.network import NetworkClient
# import info as data
from fabric.utils.helpers import exec_shell_command_async, invoke_repeater
import icons.icons as icons
import psutil

class NetworkApplet(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar", **kwargs)
        self.download_label = Label(name="download-label", markup="Download: 0 B/s")
        self.network_client = NetworkClient()
        self.upload_label = Label(name="upload-label", markup="Upload: 0 B/s")
        self.wifi_label = Label(name="network-icon-label", markup="WiFi: Unknown")

        self.is_mouse_over = False

        self.download_icon = Label(name="download-icon-label", markup=icons.download)
        self.upload_icon = Label(name="upload-icon-label", markup=icons.upload)

        self.download_box = Box(
            children=[self.download_icon, self.download_label],
        )

        self.upload_box = Box(
            children=[self.upload_label, self.upload_icon],
        )

        self.download_revealer = Revealer(child=self.download_box, transition_type = "slide-right", child_revealed=False)
        self.upload_revealer = Revealer(child=self.upload_box, transition_type="slide-left" ,child_revealed=False)
        

        self.children = Box(
            children=[self.upload_revealer, self.wifi_label, self.download_revealer],
        )
        self.last_counters = psutil.net_io_counters()
        self.last_time = time.time()
        invoke_repeater(1000, self.update_network)

        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

    def update_network(self):
        current_time = time.time()
        elapsed = current_time - self.last_time
        current_counters = psutil.net_io_counters()
        download_speed = (current_counters.bytes_recv - self.last_counters.bytes_recv) / elapsed
        upload_speed = (current_counters.bytes_sent - self.last_counters.bytes_sent) / elapsed
        download_str = self.format_speed(download_speed)
        upload_str = self.format_speed(upload_speed)
        self.download_label.set_markup(download_str)
        self.upload_label.set_markup(upload_str)

        self.downloading = (download_speed >= 10e6)
        self.uploading = (upload_speed >= 2e6)

        # Apply urgent styles regardless of orientation
        if self.downloading and not self.is_mouse_over:
            self.download_urgent()
        if self.uploading and not self.is_mouse_over:
            self.upload_urgent()
        
        if not self.downloading and not self.uploading:
            self.remove_urgent()

        if not data.VERTICAL:
            # Horizontal mode - original behavior for revealers
            self.download_revealer.set_reveal_child(self.downloading or self.is_mouse_over)
            self.upload_revealer.set_reveal_child(self.uploading or self.is_mouse_over)
        else:
            # Vertical mode - don't use revealers, change icon instead
            self.download_revealer.set_reveal_child(False)
            self.upload_revealer.set_reveal_child(False)
        
        if self.network_client and self.network_client.wifi_device:
            if self.network_client.wifi_device.ssid != "Disconnected":
                strength = self.network_client.wifi_device.strength
                
                if data.VERTICAL:
                    # Change the WiFi icon based on network activity
                    if self.downloading:
                        self.wifi_label.set_markup(icons.download)
                    elif self.uploading:
                        self.wifi_label.set_markup(icons.upload)
                    else:
                        # Normal WiFi icon based on signal strength
                        if strength >= 75:
                            self.wifi_label.set_markup(icons.wifi_3)
                        elif strength >= 50:
                            self.wifi_label.set_markup(icons.wifi_2)
                        elif strength >= 25:
                            self.wifi_label.set_markup(icons.wifi_1)
                        else:
                            self.wifi_label.set_markup(icons.wifi_0)
                    
                    # Vertical mode format for tooltip
                    self.set_tooltip_text(f"SSID: {self.network_client.wifi_device.ssid}\nDownload: {download_str}\nUpload: {upload_str}")
                else:
                    # Original horizontal mode
                    if strength >= 75:
                        self.wifi_label.set_markup(icons.wifi_3)
                    elif strength >= 50:
                        self.wifi_label.set_markup(icons.wifi_2)
                    elif strength >= 25:
                        self.wifi_label.set_markup(icons.wifi_1)
                    else:
                        self.wifi_label.set_markup(icons.wifi_0)

                    self.set_tooltip_text(self.network_client.wifi_device.ssid)
            else:
                self.wifi_label.set_markup(icons.world_off)
                self.set_tooltip_text("Disconnected")
        else:
            self.wifi_label.set_markup(icons.world_off)
            self.set_tooltip_text("Disconnected")

        self.last_counters = current_counters
        self.last_time = current_time
        return True

    def format_speed(self, speed):
        if speed < 1024:
            return f"{speed:.0f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        
    def on_mouse_enter(self, *_):
        self.is_mouse_over = True
        if not data.VERTICAL:
            self.remove_urgent()
            self.download_revealer.set_reveal_child(True)
            self.upload_revealer.set_reveal_child(True)
        return
    
    def on_mouse_leave(self, *_):
        self.is_mouse_over = False
        if not data.VERTICAL:
            self.remove_urgent()
            self.download_revealer.set_reveal_child(False)
            self.upload_revealer.set_reveal_child(False)
        return

    def upload_urgent(self):
        self.add_style_class("upload")
        self.wifi_label.add_style_class("urgent")
        self.upload_label.add_style_class("urgent")
        self.upload_icon.add_style_class("urgent")
        self.download_icon.add_style_class("urgent")
        self.upload_revealer.set_reveal_child(True)
        self.download_revealer.set_reveal_child(self.downloading)
        return
    
    def download_urgent(self):
        self.add_style_class("download")
        self.wifi_label.add_style_class("urgent")
        self.download_label.add_style_class("urgent")
        self.download_icon.add_style_class("urgent")
        self.upload_icon.add_style_class("urgent")
        self.download_revealer.set_reveal_child(True)
        self.upload_revealer.set_reveal_child(self.uploading)
        return
    
    def remove_urgent(self):
        self.remove_style_class("download")
        self.remove_style_class("upload")
        self.wifi_label.remove_style_class("urgent")
        self.download_label.remove_style_class("urgent")
        self.upload_label.remove_style_class("urgent")
        self.download_icon.remove_style_class("urgent")
        self.upload_icon.remove_style_class("urgent")
        return