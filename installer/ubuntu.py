"""Ubuntu / Debian backend: apt for packages, cargo + meson for the rest."""
from __future__ import annotations

import re
from typing import Dict, List

from common import (BIN_DIR, CARGO_BIN, VENDOR_DIR, Backend, Plan, Problem, Tool,
                    capture, run)

# Let apt/dpkg deal with other package managers (unattended-upgrades, update-notifier...):
# if the dpkg lock is held, wait up to 5 minutes instead of failing.
APT = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-o", "DPkg::Lock::Timeout=300"]

GTK_SESSION_LOCK_TYPELIBS = (
    "/usr/lib/girepository-1.0/GtkSessionLock-*.typelib",
    "/usr/lib/*/girepository-1.0/GtkSessionLock-*.typelib",
    "/usr/local/lib/*/girepository-1.0/GtkSessionLock-*.typelib",
)


class UbuntuBackend(Backend):
    name = "ubuntu"
    pretty = "Ubuntu / Debian"
    VENV_SYSTEM_SITE = False

    PACKAGES: Dict[str, List[str]] = {
        "core": [
            "build-essential", "pkg-config", "git", "curl", "meson", "ninja-build", "valac",
            "python3-dev", "python3-venv", "python3-pip",
            "libcairo2-dev", "libgirepository1.0-dev", "libgtk-3-dev", "libdbusmenu-gtk3-dev",
            "gir1.2-playerctl-2.0", "brightnessctl",
        ],
        "x11": ["feh", "picom"],
        "wayland": [
            "swaybg", "wl-clipboard",
            "gir1.2-gtklayershell-0.1", "libgtk-layer-shell0",
            # build deps for gtk-session-lock (not packaged on Ubuntu 24.04, built below)
            "libwayland-dev", "gobject-introspection", "gtk-doc-tools",
        ],
    }

    # Built from source. `requires` is verified in PRE-FLIGHT, and only if the tool is actually missing.
    TOOLS: List[Tool] = [
        Tool("matugen", "matugen", "core", ("cargo",), "build_matugen", ("https://index.crates.io/config.json",)),
        Tool("fabric-cli", "fabric-cli", "core", ("go",), "build_fabric_cli"),
        Tool("gray", "gray", "core", (), "build_gray"),
        Tool("gtk-session-lock", "", "wayland", (), "build_gtk_session_lock", (), GTK_SESSION_LOCK_TYPELIBS),
    ]

    # ---- queries -------------------------------------------------------------
    def missing_pkgs(self, pkgs: List[str]) -> List[str]:
        _, out = capture(["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\\n"] + pkgs)
        installed = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("ii"):
                installed.add(parts[0])
        return [p for p in pkgs if p not in installed]

    # ---- pre-flight ----------------------------------------------------------
    def prepare(self) -> None:
        run(APT + ["update"], sudo=True, label="Refreshing apt package index")

    def check_packages(self, missing: List[str]) -> List[Problem]:
        bad = []
        for p in missing:
            _, out = capture(["apt-cache", "policy", p])
            m = re.search(r"Candidate:\s*(\S+)", out)
            if not m or m.group(1) == "(none)":
                bad.append(p)
        if not bad:
            return []
        return [Problem("Not available from your apt sources: " + ", ".join(bad),
                        "Enable 'universe' (sudo add-apt-repository universe) and re-run.\n"
                        "Some Wayland packages only exist on newer releases (e.g. Ubuntu 24.04+).")]

    def extra_hosts(self, plan: Plan) -> List[str]:
        return []

    def prereq_fixers(self):
        return {
            "cargo": ("install the Rust toolchain via the official rustup installer (to ~/.cargo)", self._fix_cargo),
            "go": ("install golang-go via apt", self._fix_go),
        }

    def _fix_cargo(self) -> None:
        run(["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal"],
            label="Installing Rust toolchain (rustup)")

    def _fix_go(self) -> None:
        run(APT + ["install", "-y", "golang-go"], sudo=True, label="Installing Go (golang-go)")

    # ---- install -------------------------------------------------------------
    def install_packages(self, plan: Plan) -> None:
        run(APT + ["install", "-y"] + plan.missing_pkgs, sudo=True,
            label="Installing %d packages (apt)" % len(plan.missing_pkgs))

    def _vendor(self, name: str, url: str):
        d = VENDOR_DIR / name
        if not d.exists():
            VENDOR_DIR.mkdir(parents=True, exist_ok=True)
            run(["git", "clone", "--depth=1", url, d], label="Cloning %s" % name)
        return d

    def _meson_setup(self, d, *args: str) -> None:
        cmd = ["meson", "setup"] + list(args) + ["build"]
        if (d / "build").exists():
            cmd.insert(2, "--reconfigure")
        run(cmd, cwd=d, label="Configuring %s" % d.name)

    def build_matugen(self) -> None:
        run(["cargo", "install", "matugen", "--locked"], label="Building matugen (cargo – takes a few minutes)")
        # make sure the session (not just this installer) finds it
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        src, link = CARGO_BIN / "matugen", BIN_DIR / "matugen"
        if src.exists() and not link.exists():
            link.symlink_to(src)

    def build_fabric_cli(self) -> None:
        d = self._vendor("fabric-cli", "https://github.com/Fabric-Development/fabric-cli.git")
        self._meson_setup(d, "--buildtype=release", "--prefix=/usr")
        run(["meson", "install", "-C", "build"], sudo=True, cwd=d, label="Building & installing fabric-cli")

    def build_gray(self) -> None:
        d = self._vendor("gray", "https://github.com/Fabric-Development/gray.git")
        self._meson_setup(d, "--prefix=/usr")
        run(["ninja", "-C", "build", "install"], sudo=True, cwd=d, label="Building & installing gray")

    def build_gtk_session_lock(self) -> None:
        d = self._vendor("gtk-session-lock", "https://github.com/Cu3PO42/gtk-session-lock.git")
        self._meson_setup(d, "--prefix=/usr")  # /usr so GObject-introspection finds the typelib
        run(["ninja", "-C", "build"], cwd=d, label="Compiling gtk-session-lock")
        run(["ninja", "-C", "build", "install"], sudo=True, cwd=d, label="Installing gtk-session-lock")
        run(["ldconfig"], sudo=True, label="Refreshing linker cache")