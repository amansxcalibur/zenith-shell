"""Arch Linux backend: pacman for repo packages, an AUR helper for the rest."""

from __future__ import annotations

import json
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from common import Backend, InstallError, Plan, Problem, capture, have, info, run, warn


class ArchBackend(Backend):
    name = "arch"
    pretty = "Arch Linux"
    VENV_SYSTEM_SITE = True  # python-gobject comes from pacman

    # One flat list: each name is resolved to "official repo" or "AUR" automatically,
    # so you never have to maintain two lists (and a package moving repos can't break the installer).
    PACKAGES: dict[str, list[str]] = {  # noqa: RUF012
        "core": [
            "base-devel",
            "git",
            "curl",
            "python",
            "python-gobject",
            "python-cairo",
            "gtk3",
            "libdbusmenu-gtk3",
            "gobject-introspection",
            "gnome-bluetooth-3.0",
            "brightnessctl",
            "playerctl",
            "libnotify",
            "matugen-bin",
            "fabric-cli-git",
            "gray-git",
        ],
        "x11": ["feh", "picom"],
        "wayland": ["swaybg", "wl-clipboard", "gtk-layer-shell", "gtk-session-lock"],
    }

    def __init__(self) -> None:
        self._cls: tuple[list[str], list[str], list[str], bool] | None = None

    # ---- queries -------------------------------------------------------------
    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        # `pacman -T` prints the unsatisfied ones (and honours "provides")
        rc, out = capture(["pacman", "-T"] + pkgs)
        return out.split() if rc != 0 else []

    def _aur_lookup(self, names: list[str]) -> set[str]:
        query = "&".join("arg[]=" + urllib.parse.quote(n) for n in names)
        with urllib.request.urlopen(
            "https://aur.archlinux.org/rpc/v5/info?" + query, timeout=10
        ) as r:
            data = json.load(r)
        return {x["Name"] for x in data.get("results", [])}

    def _classify(
        self, pkgs: list[str]
    ) -> tuple[list[str], list[str], list[str], bool]:
        """-> (official, aur, unknown, aur_lookup_worked)"""
        if self._cls is not None:
            return self._cls
        repo = [p for p in pkgs if capture(["pacman", "-Si", p])[0] == 0]
        rest = [p for p in pkgs if p not in repo]
        aur: list[str] = []
        unknown: list[str] = []
        worked = True
        if rest:
            try:
                found = self._aur_lookup(rest)
            except Exception:
                found, worked = set(rest), False
            aur = [p for p in rest if p in found]
            unknown = [p for p in rest if p not in found]
        self._cls = (repo, aur, unknown, worked)
        return self._cls

    # ---- pre-flight ----------------------------------------------------------
    def check_packages(self, missing: list[str]) -> list[Problem]:
        _, _, unknown, _ = self._classify(missing)
        if not unknown:
            return []
        return [
            Problem(
                "Not found in the official repos or the AUR: " + ", ".join(unknown),
                "Check the spelling, or run `sudo pacman -Syu` if a repo package is new.",
            )
        ]

    def system_checks(self, plan: Plan) -> list[Problem]:
        P: list[Problem] = []
        if not have("pacman"):
            P.append(Problem("pacman not found – is this really Arch?"))
        if Path("/var/lib/pacman/db.lck").exists():
            P.append(
                Problem(
                    "pacman database is locked (/var/lib/pacman/db.lck).",
                    "Close other package managers; if none is running: sudo rm /var/lib/pacman/db.lck",
                )
            )
        return P

    def extra_hosts(self, plan: Plan) -> list[str]:
        return ["https://aur.archlinux.org"] if plan.missing_pkgs else []

    # ---- install -------------------------------------------------------------
    def _ensure_helper(self) -> str:
        for h in ("paru", "yay"):
            if have(h):
                return h
        info("No AUR helper found – building yay-bin.")
        tmp = Path(tempfile.mkdtemp(prefix="zenith-yay-"))
        try:
            run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "https://aur.archlinux.org/yay-bin.git",
                    tmp / "yay-bin",
                ],
                label="Cloning yay-bin",
            )
            run(
                ["makepkg", "-si", "--noconfirm"],
                cwd=tmp / "yay-bin",
                label="Building yay-bin",
            )
        finally:
            import shutil

            shutil.rmtree(str(tmp), ignore_errors=True)
        return "yay"

    def install_packages(self, plan: Plan) -> None:
        repo, aur, unknown, worked = self._classify(plan.missing_pkgs)
        if unknown:
            raise InstallError("unresolved packages: " + ", ".join(unknown))
        if not worked:
            warn("AUR lookup failed; assuming non-repo packages are in the AUR.")
        if repo:
            run(
                ["pacman", "-S", "--needed", "--noconfirm"] + repo,
                sudo=True,
                label="Installing %d packages (pacman)" % len(repo),
            )
        if aur:
            helper = self._ensure_helper()
            run(
                [helper, "-S", "--needed", "--noconfirm"] + aur,
                label="Installing %d AUR packages (%s)" % (len(aur), helper),
            )
