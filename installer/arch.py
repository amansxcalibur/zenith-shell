"""Arch Linux backend: pacman for repo packages, an AUR helper for the rest."""

import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from common import Backend, InstallError, Plan, Problem, capture, have, info, run, warn


class ArchBackend(Backend):
    name = "arch"
    pretty = "Arch Linux"
    REMOVE_CMD = "sudo pacman -Rns"
    VENV_SYSTEM_SITE = True  # python-gobject comes from pacman

    # One flat list: each name is resolved to "official repo" or "AUR" automatically,
    # so you never maintain two lists (and a package moving repos can't break the installer).
    PACKAGES = {  # noqa: RUF012
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
        self._classified: tuple[list[str], list[str], list[str], bool] | None = None

    # ---- queries -------------------------------------------------------------
    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        # `pacman -T` prints the unsatisfied ones (and honours "provides")
        rc, out = capture(["pacman", "-T", *pkgs])
        return out.split() if rc != 0 else []

    def _aur_lookup(self, names: list[str]) -> set[str]:
        query = "&".join(f"arg[]={urllib.parse.quote(name)}" for name in names)
        with urllib.request.urlopen(
            f"https://aur.archlinux.org/rpc/v5/info?{query}", timeout=10
        ) as response:
            data = json.load(response)
        return {item["Name"] for item in data.get("results", [])}

    def _classify(
        self, pkgs: list[str]
    ) -> tuple[list[str], list[str], list[str], bool]:
        """-> (official, aur, unknown, aur_lookup_worked)"""
        if self._classified is not None:
            return self._classified
        repo = [p for p in pkgs if capture(["pacman", "-Si", p])[0] == 0]
        rest = [p for p in pkgs if p not in repo]
        aur: list[str] = []
        unknown: list[str] = []
        worked = True
        if rest:
            try:
                found = self._aur_lookup(rest)
            except Exception:  #  (offline: the network check reports it)
                found, worked = set(rest), False
            aur = [p for p in rest if p in found]
            unknown = [p for p in rest if p not in found]
        self._classified = (repo, aur, unknown, worked)
        return self._classified

    # ---- pre-flight ----------------------------------------------------------
    def check_packages(self, missing: list[str]) -> list[Problem]:
        _, _, unknown, _ = self._classify(missing)
        if not unknown:
            return []
        return [
            Problem(
                f"Not found in the official repos or the AUR: {', '.join(unknown)}",
                "Check the spelling, or run `sudo pacman -Syu` if a repo package is new.",
            )
        ]

    def system_checks(self, plan: Plan) -> list[Problem]:
        problems: list[Problem] = []
        if not have("pacman"):
            problems.append(Problem("pacman not found – is this really Arch?"))
        if Path("/var/lib/pacman/db.lck").exists():
            problems.append(
                Problem(
                    "pacman database is locked (/var/lib/pacman/db.lck).",
                    "Close other package managers; if none is running: "
                    "sudo rm /var/lib/pacman/db.lck",
                )
            )
        return problems

    def extra_hosts(self, plan: Plan) -> list[str]:
        return ["https://aur.archlinux.org"] if plan.missing_pkgs else []

    # ---- install -------------------------------------------------------------
    def _ensure_helper(self) -> str:
        for helper in ("paru", "yay"):
            if have(helper):
                return helper
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
            shutil.rmtree(tmp, ignore_errors=True)
        return "yay"

    def install_packages(self, plan: Plan) -> None:
        repo, aur, unknown, worked = self._classify(plan.missing_pkgs)
        if unknown:
            raise InstallError(f"Unresolved packages: {', '.join(unknown)}")
        if not worked:
            warn("AUR lookup failed; assuming non-repo packages are in the AUR.")
        if repo:
            run(
                ["pacman", "-S", "--needed", "--noconfirm", *repo],
                sudo=True,
                label=f"Installing {len(repo)} packages (pacman)",
            )
        if aur:
            helper = self._ensure_helper()
            run(
                [helper, "-S", "--needed", "--noconfirm", *aur],
                label=f"Installing {len(aur)} AUR packages ({helper})",
            )
