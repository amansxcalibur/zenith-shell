"""Arch Linux backend: pacman for repo packages, an AUR helper for the rest."""

import json
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from common import (
    Backend,
    InstallError,
    Plan,
    Problem,
    Tool,
    capture,
    have,
    info,
    run,
    warn,
)

Classified = tuple[list[str], list[str], list[str], bool]

SYNC_DIR = Path("/var/lib/pacman/sync")
STALE_DB_DAYS = 14
GRAY_URL = "https://github.com/Fabric-Development/gray.git"


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
            # build dependencies for gray (built from source, see TOOLS)
            "meson",
            "ninja",
            "vala",
        ],
        "x11": ["feh", "picom"],
        "wayland": ["swaybg", "wl-clipboard", "gtk-layer-shell", "gtk-session-lock"],
    }

    # gray-git (AUR) installs straight into /usr instead of $pkgdir and breaks without a
    # terminal, so it is built from upstream instead, like on Ubuntu. Its build tools come
    # from PACKAGES above, which are installed before tools are built.
    TOOLS = [  # noqa: RUF012
        Tool(
            "gray",
            cmd="",
            feature="core",
            build="build_gray",
            hosts=("https://github.com",),
            files=("/usr/lib/girepository-1.0/Gray-0.1.typelib",),
        ),
    ]

    # `pacman -T` only follows "provides" one way: matugen-bin provides matugen, but an
    # installed matugen does not satisfy matugen-bin (and the two conflict, so installing
    # the -bin on top would fail under --noconfirm). Treat these as already satisfied.
    ALTERNATIVES = {"matugen-bin": ["matugen"]}  # noqa: RUF012

    def __init__(self) -> None:
        self._classified: dict[tuple[str, ...], Classified] = {}

    # ---- queries -------------------------------------------------------------
    def _satisfied(self, pkg: str) -> bool:
        return capture(["pacman", "-T", pkg])[0] == 0

    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        # `pacman -T` prints the unsatisfied ones (and honours "provides")
        rc, out = capture(["pacman", "-T", *pkgs])
        missing = out.split() if rc != 0 else []
        return [
            p
            for p in missing
            if not any(self._satisfied(alt) for alt in self.ALTERNATIVES.get(p, []))
        ]

    def _aur_lookup(self, names: list[str]) -> set[str]:
        query = "&".join(f"arg[]={urllib.parse.quote(name)}" for name in names)
        with urllib.request.urlopen(
            f"https://aur.archlinux.org/rpc/v5/info?{query}", timeout=10
        ) as response:
            data = json.load(response)
        return {item["Name"] for item in data.get("results", [])}

    def _classify(self, pkgs: list[str]) -> Classified:
        """-> (official, aur, unknown, aur_lookup_worked). Cached per package list."""
        key = tuple(pkgs)
        if key in self._classified:
            return self._classified[key]
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
        self._classified[key] = (repo, aur, unknown, worked)
        return self._classified[key]

    # ---- pre-flight ----------------------------------------------------------
    def prepare(self) -> None:
        # No `-Sy` here: refreshing the db without upgrading is an unsupported partial
        # upgrade on Arch. A stale db is only a problem for classification and for
        # downloads, so just tell the user.
        dbs = list(SYNC_DIR.glob("*.db"))
        if not dbs:
            warn(
                "pacman sync databases are missing. Run `sudo pacman -Syu` first, "
                "otherwise repo packages may be reported as not found."
            )
            return
        age_days = (time.time() - max(p.stat().st_mtime for p in dbs)) / 86400
        if age_days > STALE_DB_DAYS:
            warn(
                f"pacman databases were last synced {int(age_days)} days ago. "
                "Consider `sudo pacman -Syu` first to avoid 404s and misclassified packages."
            )

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

    def plan_notes(self, plan: Plan) -> list[str]:
        """Extra lines for the Plan panel: say which packages come from the AUR."""
        if not plan.missing_pkgs:
            return []
        _, aur, _, _ = self._classify(plan.missing_pkgs)
        if not aur:
            return []
        return [
            f"AUR        : {' '.join(aur)}",
            "             built from community PKGBUILDs, installed without review (--noconfirm)",
        ]

    # ---- install -------------------------------------------------------------
    def _ensure_helper(self) -> str:
        for helper in ("paru", "yay"):
            if have(helper):
                return helper
        info("No AUR helper found. Building yay-bin.")
        tmp = Path(tempfile.mkdtemp(prefix="zenith-yay-"))
        try:
            src = tmp / "yay-bin"
            run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "https://aur.archlinux.org/yay-bin.git",
                    src,
                ],
                label="Cloning yay-bin",
            )
            run(["makepkg", "--noconfirm"], cwd=src, label="Building yay-bin")
            rc, out = capture(["makepkg", "--packagelist"], cwd=src)
            built = [
                Path(line)
                for line in out.splitlines()
                if line and "-debug" not in Path(line).name and Path(line).exists()
            ]
            if rc != 0 or not built:
                raise InstallError("makepkg produced no package for yay-bin.")
            run(
                ["pacman", "-U", "--noconfirm", *built],
                sudo=True,
                label="Installing yay-bin",
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
                [helper, "-S", "--needed", "--noconfirm", "--sudoflags=-n", *aur],
                label=f"Installing {len(aur)} AUR packages ({helper})",
            )

    # ---- tools built from source ---------------------------------------------
    def build_gray(self) -> None:
        self.build_meson("gray", GRAY_URL)

    def uninstall_tools(self, names: list[str]) -> None:
        for name in names:
            self.uninstall_meson(name)
