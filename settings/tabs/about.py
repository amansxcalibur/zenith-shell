import json
import platform
import subprocess
from functools import lru_cache
from importlib import metadata

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button

import icons

from config.info import IS_WAYLAND, ROOT_DIR

from utils.cursor import add_hover_cursor

from widgets.variable_font_label import VariableFontLabel, VariableIconLabel
from widgets.zenith_logo import ZenithLogo

from wm import get_wm

from ..state import state
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
def _version_info() -> dict:
    try:
        info = json.loads((ROOT_DIR / "version.json").read_text())
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def zenith_version() -> str:
    version = _version_info().get("version")
    if not isinstance(version, str) or not version:
        return UNRELEASED_VERSION
    return version if version.startswith("v") else f"v{version}"


def zenith_release_name() -> str | None:
    name = _version_info().get("name")
    return name if isinstance(name, str) and name else None


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

        session = f"{'Wayland' if IS_WAYLAND else 'X11'} · {get_wm().label}"

        summary = Box(
            orientation="v",
            spacing=4,
            v_align="center",
            h_expand=True,
            children=[
                VariableFontLabel(
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
                        name="about-version",
                        label=" · ".join(
                            filter(None, [zenith_version(), zenith_release_name()])
                        ),
                        selectable=True,
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

        update_switch = Gtk.Switch(
            name="matugen-switcher",
            active=bool(state.get(["system", "UPDATE_CHECK"])),
        )
        update_switch.set_valign(Gtk.Align.CENTER)
        update_switch.connect(
            "notify::active",
            lambda switch, _pspec: state.update(
                ["system", "UPDATE_CHECK"], switch.get_active()
            ),
        )

        height_strut = Label(label="", style_classes="settings-height-strut")
        height_strut.set_opacity(0)

        update_row = Box(
            style_classes=["settings-item", "settings-item-wide"],
            spacing=14,
            children=[
                VariableIconLabel(
                    icon_text=icons.material.update.symbol(),
                    font_size=17,
                    h_expand=False,
                ),
                Box(
                    orientation="v",
                    h_expand=True,
                    v_align="center",
                    children=[
                        Label(label="Check for updates", h_align="start"),
                        Label(
                            label="Major and minor releases",
                            style_classes="module-hint",
                            h_align="start",
                        ),
                    ],
                ),
                Box(children=[height_strut, update_switch]),
            ],
        )
        self.container.add(
            LayoutBuilder.section(
                "Updates",
                LayoutBuilder.settings_list([update_row], lambda row: row),
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
                                VariableIconLabel(
                                    icon_text=icons.material.code.symbol(), font_size=17
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
