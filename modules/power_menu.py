from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.utils.helpers import exec_shell_command_async

from widgets.material_label import MaterialIconLabel
from utils.lock import lock_screen

import icons
from config.info import SHELL_NAME


class PowerMenu(Box):
    def __init__(self, **kwargs):
        super().__init__(name="power-menu", spacing=3, **kwargs)

        self.btn_lock = Button(
            style_classes="menu-item",
            on_clicked=self.lock,
            child=MaterialIconLabel(style_classes="menu-label", wght=600, icon_text=icons.lock.symbol()),
        )
        self.btn_suspend = Button(
            style_classes="menu-item",
            on_clicked=self.suspend,
            child=MaterialIconLabel(style_classes="menu-label", wght=600, icon_text=icons.suspend.symbol()),
        )
        self.btn_logout = Button(
            style_classes="menu-item",
            on_clicked=self.logout,
            child=MaterialIconLabel(style_classes="menu-label", wght=600, icon_text=icons.logout.symbol()),
        )
        self.btn_reboot = Button(
            style_classes="menu-item",
            on_clicked=self.reboot,
            child=MaterialIconLabel(style_classes="menu-label", wght=600, icon_text=icons.reboot.symbol()),
        )
        self.btn_shutdown = Button(
            style_classes="menu-item",
            on_clicked=self.shutdown,
            child=MaterialIconLabel(style_classes="menu-label", wght=600, icon_text=icons.shutdown.symbol()),
        )

        self.children = [
            self.btn_lock,
            self.btn_suspend,
            self.btn_logout,
            self.btn_reboot,
            self.btn_shutdown,
        ]

    def lock(self, *_):
        print("Locking...")
        self.close_power_menu()
        lock_screen()

    def suspend(self, *_):
        print("Suspending...")
        self.close_power_menu()
        exec_shell_command_async("systemctl suspend")

    def logout(self, *_):
        print("Logging out...")
        self.close_power_menu()
        exec_shell_command_async("i3-msg exit")

    def reboot(self, *_):
        print("Rebooting...")
        self.close_power_menu()
        exec_shell_command_async("shutdown -r now")

    def shutdown(self, *_):
        print("Shutting down...")
        self.close_power_menu()
        exec_shell_command_async("shutdown now")

    def close_power_menu(self):
        exec_shell_command_async(
            f"fabric-cli exec {SHELL_NAME} 'pill.toggle_power_menu()'"
        )
