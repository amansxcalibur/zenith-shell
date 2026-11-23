

from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.utils.helpers import exec_shell_command_async

from widgets.variable_font_label import VariableIconLabel
from utils.lock import lock_screen

import icons
from config.info import SHELL_NAME

from wm import get_wm


class PowerMenu(Box):
    def __init__(self, **kwargs):
        super().__init__(name="power-menu", spacing=3, **kwargs)

        self.btn_lock = Button(
            style_classes="menu-item",
            on_clicked=self.lock,
            child=VariableIconLabel(style_classes="menu-label", wght=600, icon_text=icons.material.lock.symbol()),
        )
        self.btn_suspend = Button(
            style_classes="menu-item",
            on_clicked=self.suspend,
            child=VariableIconLabel(style_classes="menu-label", wght=600, icon_text=icons.material.suspend.symbol()),
        )
        self.btn_logout = Button(
            style_classes="menu-item",
            on_clicked=self.logout,
            child=VariableIconLabel(style_classes="menu-label", wght=600, icon_text=icons.material.logout.symbol()),
        )
        self.btn_reboot = Button(
            style_classes="menu-item",
            on_clicked=self.reboot,
            child=VariableIconLabel(style_classes="menu-label", wght=600, icon_text=icons.material.reboot.symbol()),
        )
        self.btn_shutdown = Button(
            style_classes="menu-item",
            on_clicked=self.shutdown,
            child=VariableIconLabel(style_classes="menu-label", wght=600, icon_text=icons.material.shutdown.symbol()),
        )

        self.children = [
            self.btn_lock,
            self.btn_suspend,
            self.btn_logout,
            self.btn_reboot,
            self.btn_shutdown,
        ]

    def lock(self, *_):
        logger.info("Locking...")
        self.close_power_menu()
        lock_screen()

    def suspend(self, *_):
        logger.info("Suspending...")
        self.close_power_menu()
        exec_shell_command_async("systemctl suspend")

    def logout(self, *_):
        logger.info("Logging out...")
        self.close_power_menu()
        get_wm().exit_session()

    def reboot(self, *_):
        logger.info("Rebooting...")
        self.close_power_menu()
        exec_shell_command_async("shutdown -r now")

    def shutdown(self, *_):
        logger.info("Shutting down...")
        self.close_power_menu()
        exec_shell_command_async("shutdown now")

    def close_power_menu(self):
        exec_shell_command_async(
            f"fabric-cli exec {SHELL_NAME} 'pill.toggle_power_menu()'"
        )
