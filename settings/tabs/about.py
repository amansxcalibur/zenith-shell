import platform
import subprocess
from functools import lru_cache
from importlib import metadata

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button

import icons
from config.info import IS_WAYLAND, ROOT_DIR
from config.i3.utils import is_swayfx
from utils.cursor import add_hover_cursor
from widgets.material_label import MaterialFontLabel, MaterialIconLabel
from widgets.zenith_logo import ZenithLogo

from ..base import BaseWidget, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

REPOSITORY_URL = "https://github.com/amansxcalibur/zenith-shell"
TAGLINE = "A SOSS shell for i3wm and sway, crafted using fabric."
UNRELEASED_VERSION = "v0.0.0"


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT_DIR), *args],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


@lru_cache(maxsize=1)
def zenith_version() -> str:
    tag = _git("describe", "--tags", "--abbrev=0")
    if not tag:
        return UNRELEASED_VERSION
    return tag if tag.startswith("v") else f"v{tag}"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _details_grid(rows: list[tuple[str, str]]) -> Gtk.Grid:
    grid = Gtk.Grid(column_spacing=24, row_spacing=10)
    for index, (key, value) in enumerate(rows):
        grid.attach(
            Label(label=key, style_classes="about-key", h_align="start"),
            0,
            index,
            1,
            1,
        )
        grid.attach(
            Label(
                label=value,
                h_align="start",
                h_expand=True,
                selectable=True,
                ellipsization="middle",
                tooltip_text=value,
            ),
            1,
            index,
            1,
            1,
        )
    return grid


class AboutTab(BaseWidget):
    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        if IS_WAYLAND:
            session = f"Wayland · {'SwayFX' if is_swayfx() else 'Sway'}"
        else:
            session = "X11 · i3"

        summary = Box(
            orientation="v",
            spacing=4,
            v_align="center",
            h_expand=True,
            children=[
                MaterialFontLabel(
                    text="Zenith Shell", font_size=28, wght=600, h_align="start"
                ),
                Label(
                    label=TAGLINE,
                    style_classes="module-hint",
                    h_align="start",
                    line_wrap="word",
                    xalign=0,
                ),
                Box(
                    h_align="start",
                    style="margin: 4px 0 8px 0;",
                    children=Label(
                        name="about-version", label=zenith_version(), selectable=True
                    ),
                ),
                _details_grid(
                    [
                        (
                            "Commit",
                            _git("describe", "--always", "--dirty") or "unknown",
                        ),
                        (
                            "Last updated",
                            _git("log", "-1", "--format=%cd", "--date=short")
                            or "unknown",
                        ),
                        ("Session", session),
                    ]
                ),
            ],
        )
        self.container.add(
            Box(
                spacing=28,
                children=[
                    Box(v_align="center", children=ZenithLogo(size=210)),
                    summary,
                ],
            )
        )

        self.container.add(
            LayoutBuilder.section(
                "System",
                _details_grid(
                    [
                        ("Fabric", _package_version("fabric")),
                        (
                            "GTK",
                            ".".join(
                                str(part)
                                for part in (
                                    Gtk.get_major_version(),
                                    Gtk.get_minor_version(),
                                    Gtk.get_micro_version(),
                                )
                            ),
                        ),
                        ("Python", platform.python_version()),
                        ("Location", str(ROOT_DIR)),
                    ]
                ),
            )
        )
        self.container.add(
            Box(
                h_align="start",
                children=add_hover_cursor(
                    Button(
                        name="about-link",
                        child=Box(
                            spacing=8,
                            children=[
                                MaterialIconLabel(
                                    icon_text=icons.code.symbol(), font_size=17
                                ),
                                Label(label="Source code"),
                            ],
                        ),
                        tooltip_text=REPOSITORY_URL,
                        on_clicked=lambda button: Gtk.show_uri_on_window(
                            button.get_toplevel(),
                            REPOSITORY_URL,
                            Gtk.get_current_event_time(),
                        ),
                    )
                ),
            )
        )
