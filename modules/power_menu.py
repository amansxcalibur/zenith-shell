from fabric.widgets.button import Button
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.utils.helpers import exec_shell_command_async

import icons
from config.info import SCRIPTS_DIR, SHELL_NAME


class PowerMenu(Box):
    def __init__(self, **kwargs):
        super().__init__(name="power-menu", spacing=3, **kwargs)

        self.btn_lock = Button(
            style_classes="menu-item",
            on_clicked=self.lock,
            child=Label(style_classes="menu-label", markup=icons.lock),
        )
        self.btn_suspend = Button(
            style_classes="menu-item",
            on_clicked=self.suspend,
            child=Label(style_classes="menu-label", markup=icons.suspend),
        )
        self.btn_logout = Button(
            style_classes="menu-item",
            on_clicked=self.logout,
            child=Label(style_classes="menu-label", markup=icons.logout),
        )
        self.btn_reboot = Button(
            style_classes="menu-item",
            on_clicked=self.reboot,
            child=Label(style_classes="menu-label", markup=icons.reboot),
        )
        self.btn_shutdown = Button(
            style_classes="menu-item",
            on_clicked=self.shutdown,
            child=Label(style_classes="menu-label", markup=icons.shutdown),
        )

        self.children = [
            self.btn_lock,
            self.btn_suspend,
            self.btn_logout,
            self.btn_reboot,
            self.btn_shutdown,
        ]

        # to adjust certain off-center icons
        self.adjust_child = {self.btn_reboot}

        for i in self.get_children():
            if i in self.adjust_child:
                i.get_child().add_style_class("adjust")

    def lock(self, *_):
        print("Locking...")
        self.close_power_menu()
        exec_shell_command_async(f"bash {SCRIPTS_DIR}/lock.sh")

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
        exec_shell_command_async(f"fabric-cli exec {SHELL_NAME} 'notch.toggle_power_menu()'")
