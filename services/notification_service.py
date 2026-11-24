import os
from typing import cast

from fabric.core.service import Signal
from fabric.notifications.service import (
    Notification as FabricNotification,
    NotificationCloseReason,
    Notifications as FabricNotifications,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # type: ignore


# fabric's list minus markup
CAPABILITIES = ["action-icons", "actions", "body", "icon-static", "persistence"]


class Notification(FabricNotification):
    URGENCY_NORMAL = 1

    def __init__(self, id: int, raw_variant: GLib.Variant, **kwargs):
        super().__init__(id, raw_variant, **kwargs)

        if self.do_get_hint_entry("urgency") is None:
            self._urgency = self.URGENCY_NORMAL

        # fabric only keeps whole seconds
        self._time = GLib.get_real_time() / 1_000_000

        # can also be a file:// uri or an icon name
        image = self._image_file
        if image and image.startswith("file://"):
            try:
                image = GLib.filename_from_uri(image)[0]
            except GLib.Error:
                image = None
        if image and not os.path.isabs(image):
            self._app_icon = self._app_icon or image
            image = None
        self._image_file = image


class Notifications(FabricNotifications):
    @Signal
    def notification_replaced(self, notification_id: int, old: object) -> None:
        self.notify("notifications")
        # emit
        self.changed()

    def new_notification_id(self) -> int:
        # clients can pick their own ids
        notif_id = super().new_notification_id()
        while notif_id in self._notifications:
            notif_id = super().new_notification_id()
        return notif_id

    def do_handle_bus_call(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        target: str,
        params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
        user_data: object = None,
    ) -> None:
        match target:
            case "GetCapabilities":
                invocation.return_value(GLib.Variant("(as)", (CAPABILITIES,)))

            case "CloseNotification":
                if notification := self._notifications.get(int(params[0])):
                    notification.close(NotificationCloseReason.CLOSED_BY_APPLICATION)
                invocation.return_value(None)

            case "Notify":
                replaces_id = cast(int, params.get_child_value(1).unpack())
                notif_id = replaces_id or self.new_notification_id()
                old = self._notifications.get(notif_id)

                self._notifications[notif_id] = Notification(
                    id=notif_id,
                    raw_variant=params,
                    on_closed=self.do_handle_notification_closed,
                    on_action_invoked=self.do_handle_notification_action_invoke,
                )
                # emit
                if old is not None:
                    self.notification_replaced(notif_id, old)
                else:
                    self.notification_added(notif_id)

                invocation.return_value(GLib.Variant("(u)", (notif_id,)))

            case _:
                return super().do_handle_bus_call(
                    conn,
                    sender,
                    path,
                    interface,
                    target,
                    params,
                    invocation,
                    user_data,
                )

        return conn.flush()
