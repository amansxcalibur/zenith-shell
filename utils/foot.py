import os
import shutil
import signal
import subprocess
from pathlib import Path
from loguru import logger

from config.info import DATA_DIR, SHELL_NAME

from gi.repository import GLib  # type: ignore

GENERATED_COLORS = Path(DATA_DIR) / "foot.ini"
FOOT_DIR = Path(GLib.get_user_config_dir()) / "foot"
FOOT_CONFIG = FOOT_DIR / "foot.ini"
FOOT_THEME = FOOT_DIR / f"{SHELL_NAME}.ini"


def _is_valid_config(path: Path) -> bool:
    result = subprocess.run(
        ["foot", "--check-config", "-c", str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        logger.warning(f"foot doesn't accept the theme: {result.stderr.strip()}")
    return result.returncode == 0


def _ensure_include():
    include_line = f"include={FOOT_THEME}"
    content = FOOT_CONFIG.read_text() if FOOT_CONFIG.exists() else ""
    if include_line in content.splitlines():
        return
    logger.info(f"Adding the theme include to {FOOT_CONFIG}")
    # has to sit above any section, and lets the user's own colors win
    FOOT_CONFIG.write_text(f"{include_line}\n{content}")


def _can_catch(pid: int, sig: signal.Signals) -> bool:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("SigCgt:"):
            return bool(int(line.split()[1], 16) >> (sig - 1) & 1)
    return False


def _switch_running(is_light: bool):
    sig = signal.SIGUSR2 if is_light else signal.SIGUSR1
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            is_foot = (proc / "comm").read_text().strip() == "foot"
            if not is_foot or proc.stat().st_uid != os.getuid():
                continue
            # the signal kills foot versions that don't handle it
            if _can_catch(int(proc.name), sig):
                os.kill(int(proc.name), sig)
        except OSError:
            continue


def write_foot_theme(is_light: bool):
    if not shutil.which("foot") or not GENERATED_COLORS.exists():
        return

    mode_line = f"initial-color-theme={'light' if is_light else 'dark'}"
    temp_path = FOOT_THEME.with_suffix(".tmp")
    try:
        text = f"{mode_line}\n\n{GENERATED_COLORS.read_text()}"
        current = FOOT_THEME.read_text() if FOOT_THEME.exists() else ""
        if text != current:
            FOOT_DIR.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(text)
            if not _is_valid_config(temp_path):
                temp_path.unlink()
                return
            os.replace(temp_path, FOOT_THEME)
        _ensure_include()
        if not current.startswith(f"{mode_line}\n"):
            _switch_running(is_light)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        logger.error(f"Couldn't update the foot theme: {e}")
