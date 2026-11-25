from config.info import IS_WAYLAND

from wm import get_wm

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # type: ignore

if IS_WAYLAND:
    from gi.repository import GtkLayerShell  # type: ignore

# open pills, the one with the keyboard last. Exclusive focus always goes to
# the higher layer, so only the latest pill may ask for it
_open = []
_clicks = {}

REGRAB_DELAY_MS = 50


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
        get_wm().unfocus_shell_window()


def _apply() -> None:
    latest = _open[-1]
    if not IS_WAYLAND:
        get_wm().focus_shell_window(latest.WIN_ROLE)
        return
    for pill in _open[:-1]:
        GtkLayerShell.set_keyboard_mode(pill, GtkLayerShell.KeyboardMode.ON_DEMAND)
    if _has_lost_keyboard(latest):
        # hyprland only reacts to a change, and needs to see both
        GtkLayerShell.set_keyboard_mode(latest, GtkLayerShell.KeyboardMode.NONE)
        GLib.timeout_add(REGRAB_DELAY_MS, _regrab, latest)
        return
    GtkLayerShell.set_keyboard_mode(latest, GtkLayerShell.KeyboardMode.EXCLUSIVE)


def _has_lost_keyboard(pill) -> bool:
    mode = GtkLayerShell.get_keyboard_mode(pill)
    return (
        mode == GtkLayerShell.KeyboardMode.EXCLUSIVE and not pill.has_toplevel_focus()
    )


def _regrab(pill) -> bool:
    if _open and _open[-1] is pill:
        GtkLayerShell.set_keyboard_mode(pill, GtkLayerShell.KeyboardMode.EXCLUSIVE)
    return False


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
