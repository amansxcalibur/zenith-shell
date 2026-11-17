import os
import json
import requests
from loguru import logger

from fabric.utils.helpers import exec_shell_command_async

from config.config import config
from config.info import CACHE_DIR, ROOT_DIR

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # type: ignore

REMOTE_VERSION_URL = (
    "https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/version.json"
)
FIRST_CHECK_DELAY_SECONDS = 60
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 10
STATE_FILE = os.path.join(CACHE_DIR, "update_check.json")


def parse_version(value) -> tuple[int, int, int] | None:
    """'v0.2.0' / '0.2' -> (0, 2, 0)"""
    if not isinstance(value, str):
        return None
    parts = value.strip().lstrip("v").split(".")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if not 1 <= len(numbers) <= 3:
        return None
    return tuple(numbers + [0] * (3 - len(numbers)))


def _read_json(path) -> dict:
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}

# major/minor bumps count (0.1 -> 0.2) notifies, patch bumps (0.2.0 -> 0.2.1) stay silent.
# checks every 6h, notifies once per bump.
class UpdateChecker:
    def __init__(self):
        GLib.timeout_add_seconds(FIRST_CHECK_DELAY_SECONDS, self._first_check)

    def _first_check(self) -> bool:
        self._check()
        GLib.timeout_add_seconds(CHECK_INTERVAL_SECONDS, self._check)
        return False

    def _check(self) -> bool:
        if config.get("system.UPDATE_CHECK", True):
            GLib.Thread.new("update-check", self._fetch, None)
        return True  # keep the interval running; the toggle is read each time

    def _fetch(self, *_):
        try:
            response = requests.get(REMOTE_VERSION_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            remote = response.json()
        except (requests.RequestException, ValueError) as e:
            logger.debug(f"[UpdateCheck] Couldn't fetch the latest version: {e}")
            return
        if isinstance(remote, dict):
            GLib.idle_add(self._compare, remote)

    def _compare(self, remote: dict) -> bool:
        remote_version = remote.get("version")
        latest = parse_version(remote_version)
        current = parse_version(_read_json(ROOT_DIR / "version.json").get("version"))
        # compare (major, minor) only: patch bumps don't get announced
        if latest is None or current is None or latest[:2] <= current[:2]:
            return False

        notified = parse_version(_read_json(STATE_FILE).get("notified"))
        if notified is not None and notified[:2] >= latest[:2]:
            return False  # already told them about this release (or a later one)

        name = remote.get("name")
        title = f"Zenith {remote_version}" + (f" ({name})" if name else "") + " is out"
        exec_shell_command_async(
            [
                "notify-send",
                "-a",
                "Zenith",
                title,
                "Run `zenith-shell update` to get it.",
            ]
        )
        logger.info(f"[UpdateCheck] {remote_version} is available")

        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump({"notified": remote_version}, f)
        except OSError as e:
            logger.warning(f"[UpdateCheck] Couldn't save state: {e}")
        return False
