"""Ubuntu / Debian backend: apt for packages, cargo + meson for the rest."""

import re

from common import (
    BIN_DIR,
    CARGO_BIN,
    VENDOR_DIR,
    Backend,
    Plan,
    Problem,
    Tool,
    capture,
    have,
    run,
)

# Let apt/dpkg deal with other package managers (unattended-upgrades, update-notifier...):
# if the dpkg lock is held, wait up to 5 minutes instead of failing.
APT = [
    "env",
    "DEBIAN_FRONTEND=noninteractive",
    "apt-get",
    "-o",
    "DPkg::Lock::Timeout=300",
]

GTK_SESSION_LOCK_TYPELIBS = (
    "/usr/lib/girepository-1.0/GtkSessionLock-*.typelib",
    "/usr/lib/*/girepository-1.0/GtkSessionLock-*.typelib",
    "/usr/local/lib/*/girepository-1.0/GtkSessionLock-*.typelib",
)


class UbuntuBackend(Backend):
    name = "ubuntu"
    pretty = "Ubuntu / Debian"
    REMOVE_CMD = "sudo apt-get remove"
    VENV_SYSTEM_SITE = False

    PACKAGES = {  # noqa: RUF012
        "core": [
            "build-essential",
            "pkg-config",
            "git",
            "curl",
            "meson",
            "ninja-build",
            "valac",
            "python3-dev",
            "python3-venv",
            "python3-pip",
            "libcairo2-dev",
            "libgirepository1.0-dev",
            "libgtk-3-dev",
            "libdbusmenu-gtk3-dev",
            "gir1.2-playerctl-2.0",
            "brightnessctl",
            "libnotify-bin",
        ],
        "x11": ["feh", "picom"],
        "wayland": [
            "swaybg",
            "wl-clipboard",
            "gir1.2-gtklayershell-0.1",
            "libgtk-layer-shell0",
            # build deps for gtk-session-lock (not packaged on Ubuntu 24.04, built below)
            "libwayland-dev",
            "gobject-introspection",
            "gtk-doc-tools",
        ],
    }

    # Built from source. `requires` is verified in PRE-FLIGHT, and only if the tool is actually missing.
    TOOLS = [  # noqa: RUF012
        Tool(
            "matugen",
            "matugen",
            "core",
            ("cargo",),
            "build_matugen",
            ("https://index.crates.io/config.json",),
        ),
        Tool("fabric-cli", "fabric-cli", "core", ("go",), "build_fabric_cli"),
        Tool("gray", "gray", "core", (), "build_gray"),
        Tool(
            "gtk-session-lock",
            "",
            "wayland",
            (),
            "build_gtk_session_lock",
            (),
            GTK_SESSION_LOCK_TYPELIBS,
        ),
    ]

    # ---- queries -------------------------------------------------------------
    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        _, out = capture(
            ["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\\n", *pkgs]
        )
        installed = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("ii"):
                installed.add(parts[0])
        return [p for p in pkgs if p not in installed]

    # ---- pre-flight ----------------------------------------------------------
    def prepare(self) -> None:
        run([*APT, "update"], sudo=True, label="Refreshing apt package index")

    def check_packages(self, missing: list[str]) -> list[Problem]:
        bad = []
        for pkg in missing:
            _, out = capture(["apt-cache", "policy", pkg])
            candidate = re.search(r"Candidate:\s*(\S+)", out)
            if not candidate or candidate.group(1) == "(none)":
                bad.append(pkg)
        if not bad:
            return []
        return [
            Problem(
                f"Not available from your apt sources: {', '.join(bad)}",
                "Enable 'universe' (sudo add-apt-repository universe) and re-run.\n"
                "Some packages only exist on newer releases (e.g. Ubuntu 24.04+).",
            )
        ]

    def prereq_fixers(self):
        return {
            "cargo": (
                "install the Rust toolchain via the official rustup installer (to ~/.cargo)",
                self._fix_cargo,
            ),
            "go": ("install golang-go via apt", self._fix_go),
        }

    def _fix_cargo(self) -> None:
        run(
            [
                "bash",
                "-c",
                "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal",
            ],
            label="Installing Rust toolchain (rustup)",
        )

    def _fix_go(self) -> None:
        run(
            [*APT, "install", "-y", "golang-go"],
            sudo=True,
            label="Installing Go (golang-go)",
        )

    # ---- install -------------------------------------------------------------
    def install_packages(self, plan: Plan) -> None:
        run(
            [*APT, "install", "-y", *plan.missing_pkgs],
            sudo=True,
            label=f"Installing {len(plan.missing_pkgs)} packages (apt)",
        )

    def _vendor(self, name: str, url: str):
        path = VENDOR_DIR / name
        if not path.exists():
            VENDOR_DIR.mkdir(parents=True, exist_ok=True)
            run(["git", "clone", "--depth=1", url, path], label=f"Cloning {name}")
        return path

    def _meson_setup(self, path, *args: str) -> None:
        cmd = ["meson", "setup", *args, "build"]
        if (path / "build").exists():
            cmd.insert(2, "--reconfigure")
        run(cmd, cwd=path, label=f"Configuring {path.name}")

    def build_matugen(self) -> None:
        run(
            ["cargo", "install", "matugen", "--locked"],
            label="Building matugen (cargo – takes a few minutes)",
        )
        # make sure the session (not just this installer) finds it
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        src, link = CARGO_BIN / "matugen", BIN_DIR / "matugen"
        if src.exists() and not link.exists():
            link.symlink_to(src)

    def build_fabric_cli(self) -> None:
        path = self._vendor(
            "fabric-cli", "https://github.com/Fabric-Development/fabric-cli.git"
        )
        self._meson_setup(path, "--buildtype=release", "--prefix=/usr")
        run(
            ["meson", "install", "-C", "build"],
            sudo=True,
            cwd=path,
            label="Building & installing fabric-cli",
        )

    def build_gray(self) -> None:
        path = self._vendor("gray", "https://github.com/Fabric-Development/gray.git")
        self._meson_setup(path, "--prefix=/usr")
        run(
            ["ninja", "-C", "build", "install"],
            sudo=True,
            cwd=path,
            label="Building & installing gray",
        )

    def build_gtk_session_lock(self) -> None:
        path = self._vendor(
            "gtk-session-lock", "https://github.com/Cu3PO42/gtk-session-lock.git"
        )
        self._meson_setup(
            path, "--prefix=/usr"
        )  # /usr so GObject-introspection finds the typelib
        run(["ninja", "-C", "build"], cwd=path, label="Compiling gtk-session-lock")
        run(
            ["ninja", "-C", "build", "install"],
            sudo=True,
            cwd=path,
            label="Installing gtk-session-lock",
        )
        run(["ldconfig"], sudo=True, label="Refreshing linker cache")

    # ---- uninstall -----------------------------------------------------------
    def uninstall_tools(self, names: list[str]) -> None:
        for name in names:
            if name == "matugen":
                if have("cargo"):
                    run(
                        ["cargo", "uninstall", "matugen"],
                        check=False,
                        label="Removing matugen",
                    )
                link = BIN_DIR / "matugen"
                if link.is_symlink():
                    link.unlink()
                continue
            path = VENDOR_DIR / name
            if (path / "build").exists():
                run(
                    ["ninja", "-C", "build", "uninstall"],
                    sudo=True,
                    cwd=path,
                    check=False,
                    label=f"Removing {name}",
                )
        if "gtk-session-lock" in names:
            run(["ldconfig"], sudo=True, check=False, label="Refreshing linker cache")
