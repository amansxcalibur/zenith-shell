from loguru import logger

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # type: ignore

from .ui import BLUE, FLASH_MS, RED, WHITE, LockContent

# same as i3lock's fixed password buffer
PASSWORD_MAX_BYTES = 512

_SUBMIT = (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
_CLEAR_CTRL = (Gdk.KEY_u, Gdk.KEY_U)


class PasswordBuffer:
    """Fixed-size UTF-8 buffer, wiped in place (never reallocated)."""

    def __init__(self, size: int = PASSWORD_MAX_BYTES):
        self._buf = bytearray(size)
        self._len = 0

    def __len__(self) -> int:
        return self._len

    def append(self, char: str) -> bool:
        data = char.encode("utf-8")
        end = self._len + len(data)
        if end > len(self._buf):
            return False
        self._buf[self._len : end] = data
        self._len = end
        return True

    def pop(self):
        # drop one UTF-8 code point: continuation bytes are 0b10xxxxxx
        while self._len:
            self._len -= 1
            byte = self._buf[self._len]
            self._buf[self._len] = 0
            if byte & 0xC0 != 0x80:
                break

    def clear(self):
        for i in range(self._len):
            self._buf[i] = 0
        self._len = 0

    def take(self) -> bytes:
        data = bytes(self._buf[: self._len])
        self.clear()
        return data


class PasswordEntry:
    """Key handling and feedback for one lock surface."""

    def __init__(self, content: LockContent, authenticator, on_success):
        self.content = content
        self.indicator = content.indicator
        self.authenticator = authenticator
        self.on_success = on_success
        self.password = PasswordBuffer()

    def handle_key(self, keysym: int, text: str, ctrl: bool):
        if self.authenticator.is_authenticating():
            return

        if keysym in _SUBMIT:
            self._submit()
        elif keysym == Gdk.KEY_BackSpace:
            self._backspace()
        elif keysym == Gdk.KEY_Escape:
            self.reset()
        elif ctrl:
            # i3lock: Ctrl+U clears; other Ctrl combos are not typed
            if keysym in _CLEAR_CTRL:
                self.reset()
        elif text:
            self._type(text)

    def reset(self):
        self.password.clear()
        self.indicator.reset()
        self.content.status.set_label("")
        self.indicator.flash(WHITE)

    def _type(self, char: str):
        if self.password.append(char):
            self.indicator.step(forward=True)
        else:
            self.indicator.flash(RED)

    def _backspace(self):
        if not len(self.password):
            self.indicator.flash(WHITE)
            return
        self.indicator.step(forward=False)
        self.password.pop()
        self.indicator.flash(RED if len(self.password) else WHITE)

    def _submit(self):
        if not len(self.password):
            return
        self.content.status.set_label("Authenticating...")
        self.indicator.hold(BLUE)
        self.authenticator.authenticate(self.password.take(), self._on_result)

    def _on_result(self, success: bool, message: str | None):
        self.indicator.release()
        if success:
            logger.info("Authentication successful - unlocking")
            self.on_success()
        else:
            logger.warning(f"Authentication failed: {message}")
            self.content.status.set_label(message or "Incorrect password")
            self.indicator.flash(RED, ms=FLASH_MS * 3)
        return False
