import os
import json
import shlex
import shutil
import functools
from enum import StrEnum
from pathlib import Path
from loguru import logger
from string import Template

from fabric.core.service import Service, Signal, Property
from fabric.utils.helpers import exec_shell_command_async, monitor_file

from config.config import config
from config.info import CACHE_DIR, CONFIG_DIR, ROOT_DIR, THEMES_DIR

from gi.repository import Gio  # type: ignore

CUSTOM_THEMES_DIR = Path(THEMES_DIR)
CATPPUCCIN_DIR = Path(CONFIG_DIR) / "catppuccin"
CATPPUCCIN_ACCENTS = (
    "rosewater",
    "flamingo",
    "pink",
    "mauve",
    "red",
    "maroon",
    "peach",
    "yellow",
    "green",
    "teal",
    "sky",
    "sapphire",
    "blue",
    "lavender",
)


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class ColorSource(StrEnum):
    MATUGEN = "matugen"
    CATPPUCCIN = "catppuccin"
    CUSTOM = "custom"


def get_custom_colors_path(theme: str, mode: ThemeMode) -> Path:
    return CUSTOM_THEMES_DIR / theme / f"{mode.value}.css"


def has_custom_colors(theme: str) -> bool:
    try:
        return any(get_custom_colors_path(theme, mode).is_file() for mode in ThemeMode)
    except OSError as e:
        logger.warning(f"Couldn't read the {theme} theme: {e}")
        return False


@functools.cache
def get_custom_themes() -> tuple[str, ...]:
    if not CUSTOM_THEMES_DIR.is_dir():
        return ()
    try:
        names = os.listdir(CUSTOM_THEMES_DIR)
    except OSError as e:
        logger.warning(f"Couldn't list {CUSTOM_THEMES_DIR}: {e}")
        return ()
    return tuple(sorted(filter(has_custom_colors, names), key=str.casefold))


def get_generated_colors_path(mode: ThemeMode) -> Path:
    return ROOT_DIR / "data" / f"colors.{mode.value}.css"


@functools.cache
def get_catppuccin_palettes() -> dict[str, dict[str, str]]:
    return json.loads((CATPPUCCIN_DIR / "palettes.json").read_text())


class ThemeService(Service):
    _instance = None

    @Signal
    def colors_changed(self) -> None: ...

    @Signal
    def theme_changed(self, mode: object) -> None: ...

    @Property(object, "readwrite")
    def theme(self) -> ThemeMode:
        return self._theme

    @theme.setter
    def theme(self, value: ThemeMode):
        if self._theme == value:
            return

        if self._apply(value):
            self._theme = value
            self.theme_config.set("mode", value.value)
            logger.info(f"Theme mode: {value.value}")
            self.emit("theme-changed", value)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self._matugen_proc = None
        self._custom_monitor = None
        self.theme_config = config.get_node("theme")
        theme_val = self.theme_config.get("mode")

        self._theme = (
            ThemeMode(theme_val)
            if theme_val in [ThemeMode.LIGHT, ThemeMode.DARK]
            else ThemeMode.DARK
        )

        source = self.theme_config.get("source")
        self.source = (
            ColorSource(source) if source in list(ColorSource) else ColorSource.MATUGEN
        )
        flavor = self.theme_config.get("flavor")
        self.flavor = flavor if flavor in get_catppuccin_palettes() else "mocha"
        accent = self.theme_config.get("accent")
        self.accent = accent if accent in CATPPUCCIN_ACCENTS else "mauve"
        themes = get_custom_themes()
        custom_theme = self.theme_config.get("custom_theme")
        self.custom_theme = (
            custom_theme if custom_theme in themes else next(iter(themes), "")
        )

        self._watch_custom_colors()
        self._apply(self._theme)
        self._initialized = True

    def set_source(self, source: ColorSource):
        if source == self.source:
            return
        self.source = source
        self.theme_config.set("source", source.value)
        logger.info(f"Color source: {source.value}")
        self._watch_custom_colors()
        self._apply(self._theme)

    def set_flavor(self, flavor: str):
        if flavor == self.flavor or flavor not in get_catppuccin_palettes():
            return
        self.flavor = flavor
        self.theme_config.set("flavor", flavor)
        if self.source == ColorSource.CATPPUCCIN:
            self._apply(self._theme)

    def set_accent(self, accent: str):
        if accent == self.accent or accent not in CATPPUCCIN_ACCENTS:
            return
        self.accent = accent
        self.theme_config.set("accent", accent)
        if self.source == ColorSource.CATPPUCCIN:
            self._apply(self._theme)

    def set_custom_theme(self, theme: str):
        if theme == self.custom_theme or theme not in get_custom_themes():
            return
        self.custom_theme = theme
        self.theme_config.set("custom_theme", theme)
        if self.source == ColorSource.CUSTOM:
            logger.info(f"Custom theme: {theme}")
            self._watch_custom_colors()
            self._apply(self._theme)

    def get_catppuccin_palette(self, mode: ThemeMode | None = None) -> dict[str, str]:
        mode = mode or self._theme
        palettes = get_catppuccin_palettes()
        return palettes["latte" if mode == ThemeMode.LIGHT else self.flavor]

    def _watch_custom_colors(self):
        if self._custom_monitor is not None:
            self._custom_monitor.cancel()
            self._custom_monitor = None
        if self.source == ColorSource.CUSTOM and self.custom_theme:
            self._custom_monitor = monitor_file(
                str(CUSTOM_THEMES_DIR / self.custom_theme),
                self._on_custom_colors_changed,
                flags="watch-moves",
            )

    def _on_custom_colors_changed(self, _monitor, file, other_file, event):
        if event not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.MOVED_IN,
            Gio.FileMonitorEvent.RENAMED,
        ):
            return
        # editors that save through a temp file report the real name as other_file
        name = (other_file or file).get_basename()
        if name == f"{self._theme.value}.css":
            self._apply(self._theme)

    def _render_catppuccin(self, mode: ThemeMode) -> Path:
        palette = self.get_catppuccin_palette(mode)
        template = Template((CATPPUCCIN_DIR / f"colors.{mode.value}.css").read_text())
        out = Path(CACHE_DIR) / "catppuccin" / f"colors.{mode.value}.css"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(template.substitute(palette, accent=palette[self.accent]))
        return out

    def _get_source_path(self, mode: ThemeMode) -> Path:
        if self.source == ColorSource.CATPPUCCIN:
            return self._render_catppuccin(mode)
        if self.source == ColorSource.CUSTOM:
            custom = get_custom_colors_path(self.custom_theme, mode)
            if self.custom_theme and custom.is_file():
                return custom
            logger.warning(
                f"No custom {mode.value} colors in {custom.parent}, using the wallpaper colors"
            )
        return get_generated_colors_path(mode)

    def _apply(self, value: ThemeMode) -> bool:
        if not isinstance(value, ThemeMode):
            logger.error(f"Invalid theme mode type: {type(value)}")
            return False

        colors_path = ROOT_DIR / "styles" / "colors.css"
        source_path = self._get_source_path(value)
        temp_path = get_generated_colors_path(value).with_suffix(".css.tmp")

        if not source_path.exists():
            logger.error(f"No color cache for mode '{value.value}': {source_path}")
            return False

        try:
            shutil.copy2(source_path, temp_path)
            os.replace(temp_path, colors_path)
            self.emit("colors-changed")
            # for anyone who includes it in their foot config
            foot_path = ROOT_DIR / "data" / f"foot.{value.value}.ini"
            if foot_path.exists():
                shutil.copy2(foot_path, foot_path.with_name("foot.ini"))
            return True
        except Exception as e:
            logger.error(f"Failed to apply theme {value.value}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def toggle_theme_mode(self) -> None:
        self.theme = ThemeMode.LIGHT if self.theme == ThemeMode.DARK else ThemeMode.DARK

    def generate_theme(self, image_path: str | Path, scheme: str) -> None:
        matugen_bin = shutil.which("matugen")
        if not matugen_bin:
            logger.error("'matugen' not found.")
            exec_shell_command_async(
                "notify-send -a 'Zenith Theme' 'Theme not updated' '\"matugen\" not found.'"
            )
            return

        image_path_str = str(image_path)
        config_path_str = str(Path(CONFIG_DIR) / "matugen" / "config.toml")

        command = " ".join(
            [
                shlex.quote(matugen_bin),
                "image",
                shlex.quote(image_path_str),
                "-t",
                shlex.quote(scheme),
                "-c",
                shlex.quote(config_path_str),
                "--source-color-index",
                "0",
            ]
        )

        try:
            if self._matugen_proc is not None:
                self._matugen_proc.force_exit()
            process, _ = exec_shell_command_async(command)
            self._matugen_proc = process

            def on_matugen_finish(p, r):
                if p is not self._matugen_proc:
                    logger.debug(
                        f"Discarded superseded matugen run for {image_path_str}"
                    )
                    return
                try:
                    p.wait_check_finish(r)
                    logger.info(
                        f"Generated the {scheme} color scheme from {image_path_str}"
                    )
                    self.theme_config.set(
                        "scheme", scheme
                    )  # set() handles same value skips
                    # kept current for switching back to matugen
                    if self.source == ColorSource.MATUGEN:
                        self._apply(self.theme)
                except Exception as e:
                    logger.error(f"Theme generation failed during execution: {e}")

            process.wait_check_async(None, on_matugen_finish)

        except Exception as e:
            logger.exception(f"Matugen process error: {e}")
