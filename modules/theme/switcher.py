from functools import partial
from collections.abc import Callable

from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.widget import Widget
from fabric.widgets.revealer import Revealer

from modules.theme.mode_button import ModeButton

from services.theme import (
    CATPPUCCIN_ACCENTS,
    CUSTOM_THEMES_DIR,
    ColorSource,
    ThemeMode,
    ThemeService,
    get_catppuccin_palettes,
    get_custom_themes,
)

from widgets.growing_panel import Backdrop, GrowingPanel, ListPanel, build_button

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # type: ignore

DEFAULT_SCHEME = "scheme-fidelity"
SCHEMES = {
    "scheme-tonal-spot": "tonal spot",
    "scheme-content": "content",
    "scheme-expressive": "expressive",
    "scheme-fidelity": "fidelity",
    "scheme-fruit-salad": "fruit salad",
    "scheme-monochrome": "monochrome",
    "scheme-neutral": "neutral",
    "scheme-rainbow": "rainbow",
}
SOURCES = {
    ColorSource.MATUGEN.value: "matugen",
    ColorSource.CATPPUCCIN.value: "catppuccin",
    ColorSource.CUSTOM.value: "custom",
}
FLAVORS = {
    "latte": "latte",
    "frappe": "frappe",
    "macchiato": "macchiato",
    "mocha": "mocha",
}
LIGHT_FLAVOR = "latte"


class AccentPanel(GrowingPanel):
    COLUMNS = 4
    SPACING = 8

    def _build_swatch(self, on_clicked, **kwargs) -> Button:
        return build_button(
            style_classes="accent-swatch",
            v_align="center",
            on_clicked=on_clicked,
            **kwargs,
        )

    def _build_resting(self) -> Button:
        return self._build_swatch(lambda *_: self.resting_clicked())

    def _build_content(self) -> Box:
        for name in CATPPUCCIN_ACCENTS:
            self.items[name] = self._build_swatch(
                lambda _, name=name: self._pick(name), tooltip_text=name.capitalize()
            )
            self.items[name].show_all()
        self._upper_rows = Box(orientation="v", spacing=self.SPACING)
        self._bottom_row = Box(spacing=self.SPACING)
        self.extras = [self._upper_rows, self._bottom_row]
        return Box(
            orientation="v",
            spacing=self.SPACING,
            children=[
                self._upper_rows,
                Box(
                    spacing=self.SPACING,
                    h_align="end",
                    children=[self._bottom_row, self.resting],
                ),
            ],
        )

    def set_palette(self, palette: dict[str, str], current: str) -> None:
        self._palette = palette
        for name, swatch in self.items.items():
            swatch.set_style(f"background-color: {palette[name]};")
        self.select(current)
        self._refresh_resting()

    def _refresh_resting(self) -> None:
        color = self._palette[self.current]
        self.resting.set_style(f"background-color: {color};")
        self.resting.set_tooltip_text(self.current.capitalize())

    def _arrange(self) -> None:
        for swatch in self.items.values():
            if parent := swatch.get_parent():
                parent.remove(swatch)
        for row in self._upper_rows.get_children():
            self._upper_rows.remove(row)

        order = self.get_order()[:-1]
        for name in order[-(self.COLUMNS - 1) :]:
            self._bottom_row.add(self.items[name])

        upper = order[: -(self.COLUMNS - 1)]
        # the short row goes on top
        first = len(upper) % self.COLUMNS
        starts = ([0] if first else []) + list(range(first, len(upper), self.COLUMNS))
        for start in starts:
            end = first if start < first else start + self.COLUMNS
            row = Box(spacing=self.SPACING, h_align="end")
            for name in upper[start:end]:
                row.add(self.items[name])
            row.show()
            self._upper_rows.add(row)


class ThemeSwitcher(Box):
    REVEAL_MS = 200
    OPTIONS_INSET = 4

    @Signal
    def scheme_picked(self, scheme: str) -> None: ...

    @Signal
    def open_changed(self, is_open: bool) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(h_align="end", v_align="end", **kwargs)
        self.theme_service = ThemeService()
        self.scheme = self._get_saved_scheme()
        # picks wait for the collapse, reloading the styles would freeze it
        self._pending: list[Callable[[], None]] = []
        self._pull_theme()

        self.mode_button = ModeButton(self._mode, v_align="end")
        self.source_panel = ListPanel(name="source-panel", padding=9)
        self.variant_panel = ListPanel(name="variant-panel", padding=5)
        self.accent_panel = AccentPanel(name="accent-panel", padding=11)
        self._panels = (self.source_panel, self.variant_panel, self.accent_panel)

        self._accent_revealer = self._build_revealer(self.accent_panel)
        self._options = Backdrop(
            lambda: self.variant_panel.get_rest_size()[1],
            name="theme-options",
            v_align="end",
            children=[self._accent_revealer, self.variant_panel],
        )
        # css margins would end up inside the painted area
        for side in ("start", "top", "bottom"):
            self._options.set_property(f"margin-{side}", self.OPTIONS_INSET)
        self._options_revealer = self._build_revealer(self._options)
        self.tray = Backdrop(
            self.get_rest_height,
            name="theme-switcher",
            children=[self._options_revealer, self.source_panel],
        )
        self.row = Box(spacing=8, children=[self.tray, self.mode_button])
        self.add(self.row)

        for panel, on_picked in (
            (self.source_panel, self._on_source_picked),
            (self.variant_panel, self._on_variant_picked),
            (self.accent_panel, self._on_accent_picked),
        ):
            panel.connect("picked", on_picked)
            panel.connect("resting-clicked", self.toggle)
            panel.connect("collapsed", lambda *_: GLib.idle_add(self._apply_pending))

        self.mode_button.connect("picked", self._on_mode_picked)
        self.mode_button.connect(
            "settled", lambda *_: GLib.idle_add(self._apply_pending)
        )

        self.theme_service.connect("colors-changed", self._on_theme_changed)
        self.theme_service.connect("theme-changed", self._on_theme_changed)
        self.connect("unmap", lambda *_: self.close())
        self._sync()

    def _build_revealer(self, child: Widget) -> Revealer:
        return Revealer(
            child=child,
            v_align="end",
            transition_type="slide-left",
            transition_duration=self.REVEAL_MS,
        )

    def _get_saved_scheme(self) -> str:
        saved = str(self.theme_service.theme_config.get("scheme") or "")
        if saved and not saved.startswith("scheme-"):
            saved = f"scheme-{saved}"
        return saved if saved in SCHEMES else DEFAULT_SCHEME

    @property
    def open_panel(self) -> GrowingPanel | None:
        return next((panel for panel in self._panels if panel.is_open), None)

    @property
    def is_open(self) -> bool:
        return self.open_panel is not None

    def _pull_theme(self) -> None:
        self._mode = self.theme_service.theme
        self._source = self.theme_service.source
        self._flavor = self._get_mode_flavor()
        self._accent = self.theme_service.accent
        self._custom_theme = self.theme_service.custom_theme

    def _get_mode_flavor(self) -> str:
        is_light = self._mode == ThemeMode.LIGHT
        return LIGHT_FLAVOR if is_light else self.theme_service.flavor

    @property
    def is_animating(self) -> bool:
        return self.mode_button.is_fading or any(
            panel.is_collapsing for panel in self._panels
        )

    def _on_theme_changed(self, *_) -> None:
        if not self._pending:
            self._pull_theme()
            self._sync()

    def _apply_pending(self) -> bool:
        if not self._pending or self.is_animating:
            return False
        # kept until done, so the service's signals don't undo what's left
        try:
            for apply in self._pending:
                apply()
        finally:
            self._pending.clear()
        self._on_theme_changed()
        return False

    def _has_accents(self) -> bool:
        return self._source == ColorSource.CATPPUCCIN

    def _get_variants(self) -> tuple[dict[str, str], str]:
        match self._source:
            case ColorSource.MATUGEN:
                return SCHEMES, self.scheme
            case ColorSource.CATPPUCCIN:
                return FLAVORS, self._flavor
            case ColorSource.CUSTOM if self._custom_theme:
                return {name: name for name in get_custom_themes()}, self._custom_theme
        return {}, ""

    def get_rest_height(self) -> int:
        return self.source_panel.get_rest_size()[1]

    def toggle(self, panel: GrowingPanel) -> None:
        if panel.is_open:
            self.close()
        elif len(panel.items) > 1:
            self._open(panel)

    def toggle_variants(self) -> None:
        has_variants = bool(self._get_variants()[0])
        self.toggle(self.variant_panel if has_variants else self.source_panel)

    def _open(self, panel: GrowingPanel) -> None:
        for other in self._panels:
            if other is not panel:
                other.close()
        panel.open()
        self._sync()
        self.open_changed(True)

    def close(self, landing: str | None = None) -> bool:
        panel = self.open_panel
        if panel is None:
            return False
        panel.close(landing)
        self._sync()
        self.open_changed(False)
        return True

    def cycle_variant(self, delta: int) -> None:
        variants, current = self._get_variants()
        if not variants:
            return
        keys = list(variants)
        self._set_variant(keys[(keys.index(current) + delta) % len(keys)])
        self._sync()
        self._apply_pending()

    def _on_source_picked(self, _panel, key: str) -> None:
        self._source = ColorSource(key)
        self._pending.append(partial(self.theme_service.set_source, self._source))
        self.close(key)

    def _on_variant_picked(self, _panel, key: str) -> None:
        self._set_variant(key)
        self.close(key)

    def _on_accent_picked(self, _panel, key: str) -> None:
        self._accent = key
        self._pending.append(partial(self.theme_service.set_accent, key))
        self.close(key)

    def _on_mode_picked(self, _toggle, mode: ThemeMode) -> None:
        if mode == self._mode:
            return
        self.close()
        self._mode = mode
        self._flavor = self._get_mode_flavor()
        self._pending.append(self._apply_mode)
        self._sync()

    def _apply_mode(self) -> None:
        self.theme_service.theme = self._mode

    def _set_variant(self, key: str) -> None:
        match self._source:
            case ColorSource.MATUGEN:
                self.scheme = key
                self._pending.append(partial(self.scheme_picked, key))
            case ColorSource.CATPPUCCIN:
                self._flavor = key
                self._mode = ThemeMode.LIGHT if key == LIGHT_FLAVOR else ThemeMode.DARK
                self._pending.append(partial(self._apply_flavor, key))
            case ColorSource.CUSTOM:
                self._custom_theme = key
                self._pending.append(partial(self.theme_service.set_custom_theme, key))

    def _apply_flavor(self, flavor: str) -> None:
        if flavor != LIGHT_FLAVOR:
            self.theme_service.set_flavor(flavor)
        self._apply_mode()

    def _sync(self) -> None:
        variants, current = self._get_variants()

        self.mode_button.show_mode(self._mode)
        self.mode_button.set_locked(self._source == ColorSource.CATPPUCCIN)
        self.source_panel.set_options(SOURCES, self._source.value)
        if not get_custom_themes():
            self.source_panel.disable_option(
                ColorSource.CUSTOM.value, f"Add a theme to {CUSTOM_THEMES_DIR}"
            )
        if variants:
            self.variant_panel.set_options(variants, current)
        if self._has_accents():
            self.accent_panel.set_palette(
                get_catppuccin_palettes()[self._flavor], self._accent
            )

        shows_accent = self._has_accents() and not self.variant_panel.is_open
        self._accent_revealer.set_reveal_child(shows_accent)
        if shows_accent:
            self.variant_panel.add_style_class("beside-accent")
        else:
            self.variant_panel.remove_style_class("beside-accent")
        shows_options = bool(variants) and not self.source_panel.is_open
        self._options_revealer.set_reveal_child(shows_options)
        if shows_options:
            self.source_panel.add_style_class("beside-options")
        else:
            self.source_panel.remove_style_class("beside-options")


class ThemeSwitcherSlot(Box):
    def __init__(self, switcher: ThemeSwitcher, **kwargs):
        super().__init__(**kwargs)
        self._switcher = switcher
        self._width_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self._width_group.add_widget(switcher.row)
        self._width_group.add_widget(self)
        self.connect("size-allocate", lambda *_: GLib.idle_add(self._pin_switcher))

    def _pin_switcher(self) -> bool:
        parent = self._switcher.get_parent()
        if parent is None or not self.get_mapped():
            return False
        x, y = self.translate_coordinates(parent, 0, 0)
        width, height = self.get_allocated_width(), self.get_allocated_height()
        leftover = max(0, height - self._switcher.get_rest_height()) // 2
        margin_end = parent.get_allocated_width() - x - width
        margin_bottom = parent.get_allocated_height() - y - height + leftover
        if self._switcher.get_margin_end() != margin_end:
            self._switcher.set_margin_end(max(0, margin_end))
        if self._switcher.get_margin_bottom() != margin_bottom:
            self._switcher.set_margin_bottom(max(0, margin_bottom))
        return False

    def do_get_preferred_height(self):
        height = self._switcher.get_rest_height()
        return height, height
