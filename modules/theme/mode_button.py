from fabric.core.service import Signal
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button

import icons

from services.theme import ThemeMode

from widgets.variable_font_label import VariableIconLabel


class ModeButton(Button):
    FADE_MS = 200
    MODE_ICONS = {  # noqa: RUF012
        ThemeMode.LIGHT: icons.material.light_mode,
        ThemeMode.DARK: icons.material.dark_mode,
    }

    @Signal
    def picked(self, mode: object) -> None: ...

    @Signal
    def settled(self) -> None: ...

    def __init__(self, mode: ThemeMode, **kwargs):
        self._mode = mode
        self.is_fading = False
        self._icons = {
            m: VariableIconLabel(icon_text=icon.symbol(), FILL=0, wght=500, opsz=24)
            for m, icon in self.MODE_ICONS.items()
        }
        self._stack = Stack(
            transition_type="crossfade",
            transition_duration=self.FADE_MS,
            children=list(self._icons.values()),
        )
        super().__init__(
            name="mode-button",
            child=self._stack,
            on_clicked=lambda *_: self.picked(self._get_next_mode()),
            **kwargs,
        )
        self.set_can_focus(False)
        self.set_focus_on_click(False)
        self._stack.set_visible_child(self._icons[mode])
        self._stack.connect("notify::transition-running", self._on_transition_changed)
        self.connect("unmap", lambda *_: self._settle())
        self._sync_tooltip()

    def show_mode(self, mode: ThemeMode) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._sync_tooltip()
        self.is_fading = True
        self._stack.set_visible_child(self._icons[mode])
        if not self._stack.get_transition_running():
            self._settle()

    def set_locked(self, is_locked: bool) -> None:
        self.set_sensitive(not is_locked)
        self._sync_tooltip()

    def _get_next_mode(self) -> ThemeMode:
        return ThemeMode.LIGHT if self._mode == ThemeMode.DARK else ThemeMode.DARK

    def _sync_tooltip(self) -> None:
        self.set_tooltip_text(
            f"Switch to {self._get_next_mode().value} mode"
            if self.get_sensitive()
            else "Set by the Catppuccin flavor"
        )

    def _on_transition_changed(self, *_) -> None:
        if self.is_fading and not self._stack.get_transition_running():
            self._settle()

    def _settle(self) -> None:
        self.is_fading = False
        self.settled()
