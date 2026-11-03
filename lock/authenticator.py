import threading
from pathlib import Path

import pam
from loguru import logger

from gi.repository import GLib  # type: ignore

# First PAM service file that exists wins. A dedicated service avoids the
# extras in "login" (securetty, nologin, lastlog, ...). i3lock's file is
# just "auth include login" on most distros, so it's a safe default.
PAM_SERVICES = ("zenith-lock", "i3lock", "login")


def _pick_pam_service() -> str:
    for service in PAM_SERVICES:
        if Path("/etc/pam.d", service).exists():
            return service
    return "login"


class Authenticator:
    def __init__(self, username: str):
        self.username = username
        self.service = _pick_pam_service()
        self._authenticating = False
        logger.debug(f"Using PAM service '{self.service}'")

    def authenticate(self, password: str | bytes, callback):
        """Authenticate in a background thread; callback runs on the main loop."""
        if self._authenticating:
            return

        self._authenticating = True

        def auth_thread():
            try:
                success = pam.authenticate(
                    self.username, password, service=self.service
                )
                if success:
                    GLib.idle_add(callback, True, None)
                else:
                    GLib.idle_add(callback, False, "Incorrect password")
            except Exception as e:
                logger.error(f"PAM authentication error: {e}")
                GLib.idle_add(callback, False, "Authentication error")
            finally:
                self._authenticating = False

        threading.Thread(target=auth_thread, daemon=True).start()

    def is_authenticating(self):
        return self._authenticating
