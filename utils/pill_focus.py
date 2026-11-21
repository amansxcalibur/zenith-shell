from config.info import IS_WAYLAND
from services.i3 import I3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore

# open pills, the one with the keyboard last. Exclusive focus always goes to
# the higher layer, so only the latest pill may ask for it
_open = []
_clicks = {}


def take_focus(pill) -> None:
    if pill in _open:
        _open.remove(pill)
    _open.append(pill)
    _watch_clicks(pill)
    _apply()


def release_focus(pill) -> None:
    if pill not in _open:
        return
    _open.remove(pill)
    if IS_WAYLAND:
        GtkLayerShell.set_keyboard_mode(pill, GtkLayerShell.KeyboardMode.NONE)
    if _open:
        _apply()
    elif not IS_WAYLAND:
        I3.send_command("focus mode_toggle")


def _apply() -> None:
    latest = _open[-1]
    if not IS_WAYLAND:
        I3.send_command(f'[window_role="^{latest.WIN_ROLE}$"] focus')
        return
    for pill in _open[:-1]:
        GtkLayerShell.set_keyboard_mode(pill, GtkLayerShell.KeyboardMode.ON_DEMAND)
    GtkLayerShell.set_keyboard_mode(latest, GtkLayerShell.KeyboardMode.EXCLUSIVE)


def _watch_clicks(pill) -> None:
    if pill in _clicks:
        return
    # capture phase, or the entries and buttons inside keep the click
    gesture = Gtk.GestureMultiPress.new(pill)
    gesture.set_button(0)
    gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    gesture.connect(
        "pressed",
        lambda *_: take_focus(pill) if pill in _open and _open[-1] is not pill else None,
    )
    _clicks[pill] = gesture
