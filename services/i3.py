import json
import socket

from loguru import logger
from fabric.i3 import widgets as fabric_i3_widgets
from fabric.i3.service import (
    I3 as FabricI3,
    I3MessageType,
    I3SocketError,
    I3SocketNotFoundError,
)
from fabric.utils.helpers import idle_add

from gi.repository import GLib  # type: ignore

RECONNECT_INTERVAL_S = 1
RECONNECT_TIMEOUT_S = 300


class I3(FabricI3):
    """Fabric's I3 service, plus reconnection when i3/sway restarts or reloads.
    Upstream: https://github.com/Fabric-Development/fabric/pull/164
    """

    def __init__(self, **kwargs):
        super(FabricI3, self).__init__(**kwargs)
        self._ready = False
        self._reconnect_source = None
        try:
            path = self.lookup_socket()
        except I3SocketNotFoundError as e:
            logger.error(f"[I3Service] initial connection failed: {e}, retrying")
            self._schedule_reconnect()
            return
        self._start_event_thread(path)

    def _start_event_thread(self, path: str):
        self.event_socket_thread = GLib.Thread.new(
            "i3-socket-service",
            self.event_socket_task,  # type: ignore
            path,
        )
        self._set_ready(True)

    def _set_ready(self, ready: bool):
        if self._ready != ready:
            self._ready = ready
            self.notify("ready")

    def event_socket_task(self, socket_addr: str) -> bool:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(socket_addr)
                sock.sendall(
                    self.pack(
                        I3MessageType.SUBSCRIBE,
                        json.dumps(
                            [
                                name.replace("_event", "")
                                for mt in I3MessageType
                                if (name := mt.name.lower()).endswith("_event")
                            ]
                        ),
                    )
                )
                self.unpack(sock)

                while True:
                    idle_add(self.handle_raw_event, *self.unpack(sock))

        except (I3SocketError, OSError) as e:
            logger.warning(f"[I3Service] lost the events socket ({e}), reconnecting")
            GLib.idle_add(self._on_disconnected)
        except Exception as e:
            logger.warning(f"[I3Service] events socket thread ended with an error: {e}")

        return False

    def _on_disconnected(self):
        self._set_ready(False)
        self._schedule_reconnect()
        return False

    def _schedule_reconnect(self):
        if self._reconnect_source is not None:
            return
        attempts = RECONNECT_TIMEOUT_S // RECONNECT_INTERVAL_S

        def try_reconnect() -> bool:
            nonlocal attempts
            attempts -= 1
            FabricI3.SOCKET_PATH = None
            try:
                path = self.lookup_socket()
            except I3SocketNotFoundError:
                if attempts > 0:
                    return True
                logger.error(
                    f"[I3Service] gave up reconnecting after {RECONNECT_TIMEOUT_S}s"
                )
                self._reconnect_source = None
                return False

            logger.info("[I3Service] socket available again, reconnected")
            self._reconnect_source = None
            self._start_event_thread(path)
            return False

        self._reconnect_source = GLib.timeout_add_seconds(
            RECONNECT_INTERVAL_S, try_reconnect
        )


def get_i3_connection() -> I3:
    if fabric_i3_widgets.connection is None:
        fabric_i3_widgets.connection = I3()
    return fabric_i3_widgets.connection


fabric_i3_widgets.get_i3_connection = get_i3_connection
