from loguru import logger
from Xlib.protocol import rq

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # type: ignore


# XKB request: UseExtension (minor opcode 0)
# Once a connection has sent this, the server reports the XKB state in core
# key events: real modifiers in bits 0-7 and the active group in bits 13-14.
# Without it, the server folds the group into compat modifiers (often Mod5),
# which is indistinguishable from AltGr.
class _XkbUseExtension(rq.ReplyRequest):
    _request = rq.Struct(
        rq.Card8("opcode"),
        rq.Opcode(0),
        rq.RequestLength(),
        rq.Card16("wanted_major"),
        rq.Card16("wanted_minor"),
    )
    _reply = rq.Struct(
        rq.ReplyCode(),
        rq.Bool("supported"),
        rq.Card16("sequence_number"),
        rq.ReplyLength(),
        rq.Card16("server_major"),
        rq.Card16("server_minor"),
        rq.Pad(20),
    )


def enable_xkb(display) -> bool:
    """Make a python-xlib connection XKB-aware. Returns True on success."""
    ext = display.query_extension("XKEYBOARD")
    if not ext.present:
        logger.warning("XKEYBOARD extension not present on this X server")
        return False
    reply = _XkbUseExtension(
        display=display.display,
        opcode=ext.major_opcode,
        wanted_major=1,
        wanted_minor=0,
    )
    if not reply.supported:
        logger.warning("X server refused XKB UseExtension 1.0")
    return bool(reply.supported)


def _xkb_group(state: int) -> int:
    return (state >> 13) & 0x3


# Input from Xlib (root-window grab), keycodes translated with GDK's keymap,
# auto tracking XKB keymap changes (YAY). That gives AltGr/level-3, a second
# layout (XKB group), NumLock on the keypad and non-Latin-1 text, which core
# keycode_to_keysym() can't.
class KeyTranslator:
    """Translate (keycode, XKB event state) -> keysym and text via GDK."""

    def __init__(self):
        self._keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())

    def keysym(self, keycode: int, state: int) -> int:
        # GDK keyvals are X keysyms
        ok, keyval, *_ = self._keymap.translate_keyboard_state(
            keycode, Gdk.ModifierType(state & 0xFF), _xkb_group(state)
        )
        return keyval if ok else 0

    @staticmethod
    def text(keysym: int) -> str:
        cp = Gdk.keyval_to_unicode(keysym)
        if not cp:
            return ""
        ch = chr(cp)
        return ch if ch.isprintable() else ""
