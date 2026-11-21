import os
import re
import shutil
import sys
from pathlib import Path

from installer.paths import (
    ASSETS_DIR,
    BIN_DIR,
    COMPLETIONS,
    FONT_DIR,
    INSTALL_DIR,
    SHELL_NAME,
    SHELL_PROCESS,
    VENV_DIR,
)
from installer.system import capture, download, have, run, venv_ok
from installer.ui import SYM, ok, warn


FONTS = {
    "RobotoFlex.ttf": "https://raw.githubusercontent.com/googlefonts/roboto-flex/main/fonts/RobotoFlex%5BGRAD%2CXOPQ%2CXTRA%2CYOPQ%2CYTAS%2CYTDE%2CYTFI%2CYTLC%2CYTUC%2Copsz%2Cslnt%2Cwdth%2Cwght%5D.ttf",
    "GoogleSansFlex.ttf": "https://raw.githubusercontent.com/amansxcalibur/zenith-resources/gh-pages/fonts/Google_Sans_Flex/GoogleSansFlex-VariableFont_GRAD%2CROND%2Copsz%2Cslnt%2Cwdth%2Cwght.ttf",
    "MaterialSymbolsRounded.ttf": "https://raw.githubusercontent.com/google/material-design-icons/master/variablefont/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf",
}


def step_python_env(backend, upgrade_pip: bool = True) -> None:
    py = VENV_DIR / "bin" / "python"
    exists = VENV_DIR.exists()
    if not exists or not venv_ok():
        # We may be running from this very venv, so build from its base interpreter.
        base = getattr(sys, "_base_executable", sys.executable)
        cmd = [base, "-m", "venv"]
        if exists:
            warn("The virtual environment is broken, rebuilding it.")
            cmd.append("--clear")
        if backend.VENV_SYSTEM_SITE:
            cmd.append("--system-site-packages")  # see python-gobject from pacman
        run([*cmd, VENV_DIR], label="Creating virtual environment")
    if upgrade_pip:
        run([py, "-m", "pip", "install", "--upgrade", "pip"], label="Upgrading pip")
    requirements = INSTALL_DIR / "requirements.txt"
    if requirements.exists():
        run(
            [py, "-m", "pip", "install", "-r", requirements],
            label="Installing Python requirements",
        )
        sync_git_pins(py, requirements)
    else:
        warn("requirements.txt not found, skipping Python deps.")


GIT_PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*@\s*(git\+\S+?)@([0-9a-f]{7,40})\s*$")


def git_pins(requirements: Path) -> list[tuple[str, str]]:
    pins = []
    for line in requirements.read_text().splitlines():
        if match := GIT_PIN.match(line):
            pins.append((match.group(1), line.strip()))
    return pins


def installed_commit(py: Path, name: str) -> str | None:
    code = (
        "import json, sys, importlib.metadata as m\n"
        "try:\n"
        "    d = json.loads(m.distribution(sys.argv[1]).read_text('direct_url.json'))\n"
        "    print(d['vcs_info']['commit_id'])\n"
        "except Exception:\n"
        "    pass\n"
    )
    rc, out = capture([py, "-c", code, name])
    return out.strip() or None if rc == 0 else None


def sync_git_pins(py: Path, requirements: Path) -> None:
    for name, line in git_pins(requirements):
        wanted = GIT_PIN.match(line).group(3)
        have = installed_commit(py, name)
        if have and have.startswith(wanted):
            continue
        run(
            [py, "-m", "pip", "install", "--force-reinstall", "--no-deps", line],
            label=f"Updating {name} to {wanted[:7]}",
        )


def step_fonts() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    fetched = False
    for name, url in FONTS.items():
        if (FONT_DIR / name).exists():
            continue
        fetched = True
        print(f"  {SYM['dot']} Downloading {name}")
        download(url, FONT_DIR / name)
    if fetched:
        run(["fc-cache", "-f"], label="Updating font cache")
    else:
        ok("Fonts present.")


LAUNCHER = (ASSETS_DIR / "launcher.sh").read_text()


def step_launchers() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    launcher = BIN_DIR / SHELL_NAME
    launcher.write_text(
        LAUNCHER.replace("@INSTALL_DIR@", str(INSTALL_DIR))
        .replace("@VENV@", str(VENV_DIR))
        .replace("@PROCESS@", SHELL_PROCESS)
    )
    launcher.chmod(0o755)
    # older installs also had a zenith-shell-setup launcher
    (BIN_DIR / f"{SHELL_NAME}-setup").unlink(missing_ok=True)
    ok(f"Launcher: {launcher.name}  (try: zenith-shell --help)")


def step_completions() -> None:
    installed = []
    for shell, (source, target) in COMPLETIONS.items():
        if not have(shell):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        installed.append(shell)
    ok(f"Tab completion: {', '.join(installed) or 'no supported shell found'}")


def step_bootstrap(wms: list[str]) -> None:
    """Write the config for each WM, whichever session the installer is running in."""
    for wm in wms:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(INSTALL_DIR)
        env["ZENITH_BOOTSTRAP_WM"] = wm
        run(
            [VENV_DIR / "bin" / "python", "-m", "config.bootstrap"],
            cwd=INSTALL_DIR,
            env=env,
            label=f"Writing {wm} config",
        )
