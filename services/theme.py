import os
import shlex
import shutil
from enum import StrEnum
from pathlib import Path
from loguru import logger

from fabric.core.service import Service, Signal, Property
from fabric.utils.helpers import exec_shell_command_async

from config.info import CONFIG_DIR, ROOT_DIR
from config.config import config


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


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

        self.theme_config = config.get_node("theme")
        theme_val = self.theme_config.get("mode")

        self._theme = (
            ThemeMode(theme_val)
            if theme_val in [ThemeMode.LIGHT, ThemeMode.DARK]
            else ThemeMode.DARK
        )

        self._apply(self._theme)
        self._initialized = True

    def _apply(self, value: ThemeMode) -> bool:
        if not isinstance(value, ThemeMode):
            logger.error(f"Invalid theme mode type: {type(value)}")
            return False

        colors_path = ROOT_DIR / "styles" / "colors.css"
        source_path = ROOT_DIR / "data" / f"colors.{value.value}.css"
        temp_path = source_path.with_suffix(".css.tmp")

        if not source_path.exists():
            logger.error(f"No color cache for mode '{value.value}': {source_path}")
            return False

        try:
            shutil.copy2(source_path, temp_path)
            os.replace(temp_path, colors_path)
            self.emit("colors-changed")
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
                "notify-send 'Zenith Shell' '\"matugen\" not found. Theme not updated.'"
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
            process, _ = exec_shell_command_async(command)

            def on_matugen_finish(p, r):
                try:
                    p.wait_check_finish(r)
                    logger.info("Theme updated")
                    self.theme_config.set(
                        "scheme", scheme
                    )  # set() handles same value skips
                    self._apply(self.theme)
                except Exception as e:
                    logger.error(f"Theme generation failed during execution: {e}")

            process.wait_check_async(None, on_matugen_finish)

        except Exception as e:
            logger.exception(f"Matugen process error: {e}")
