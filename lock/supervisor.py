# No session-lock protocol for my dear X11 :(
# If the locker process dies, the desktop is exposed. On Wayland the
# compositor keeps the session locked instead, but nothing can unlock it until
# a new locker connects. This small process (no GTK, nothing heavy imported)
# runs the real locker as a child and:
# - refuses to start a second lock (flock in $XDG_RUNTIME_DIR)
# - respawns the locker if it crashes, and falls back to i3lock/swaylock if it
#   keeps crashing
# - forwards xss-lock's XSS_SLEEP_LOCK_FD to the first child only, so suspend
#   waits until the screen is actually locked
# - with -f, returns as soon as the screen is locked and keeps supervising in
#   the background (like swaylock -f), for `swayidle -w before-sleep`

import os
import sys
import time
import fcntl
import select
import shutil
import tempfile
import subprocess
from pathlib import Path

from loguru import logger

APP_NAME = "zenith-lockscreen"

EXIT_UNLOCKED = 0
EXIT_LOCK_FAILED = 3  # X11: input grab failed, Wayland: compositor refused
EXIT_ALREADY_RUNNING = 4

SLEEP_LOCK_ENV = "XSS_SLEEP_LOCK_FD"
# -f: the locker writes one byte here once locked, then closes it
READY_ENV = "ZENITH_LOCK_READY_FD"
# how long `lock -f` waits for the lock before giving up (logind waits ~5s)
READY_TIMEOUT_S = 10

# give up on the zenith locker after this many crashes within the window
MAX_CRASHES = 3
CRASH_WINDOW_S = 30

ROOT_DIR = Path(__file__).resolve().parent.parent


def _lock_file_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(runtime) / f"{APP_NAME}-{os.getuid()}.lock"


def _acquire_single_instance():
    """Return an open, flock'ed file object, or None if another lock holds it."""
    fh = open(_lock_file_path(), "w")  # noqa: SIM115 - held for process lifetime
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


def _take_sleep_lock_fd() -> int | None:
    raw = os.environ.get(SLEEP_LOCK_ENV)
    if raw is None:
        return None
    try:
        fd = int(raw)
        os.fstat(fd)
        return fd
    except (ValueError, OSError):
        logger.warning(f"Ignoring invalid {SLEEP_LOCK_ENV}={raw!r}")
        return None


def _notify(summary: str, body: str):
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-u", "critical", "-a", "Zenith", summary, body],
            start_new_session=True,
        )


def _fallback_locker() -> int:
    from config.info import CACHE_DIR, IS_WAYLAND

    # neither forks by default; i3lock needs --nofork spelled out on some builds
    locker, cmd = (
        ("swaylock", ["swaylock"]) if IS_WAYLAND else ("i3lock", ["i3lock", "--nofork"])
    )
    if not shutil.which(locker):
        logger.critical(f"{locker} not installed; cannot fall back.")
        _notify("Lock screen crashed", f"{locker} is not installed to take over.")
        return 1

    image = Path(CACHE_DIR) / "lockscreen" / "lockscreen.png"
    cmd += ["-i", str(image)] if image.exists() else ["-c", "141315"]

    logger.warning(f"Falling back to {locker}")
    return subprocess.call(cmd)


def _lock_failed_reason() -> str:
    from config.info import IS_WAYLAND

    if IS_WAYLAND:
        return "The compositor refused the lock. Is another locker running?"
    return "Another application is holding the keyboard or mouse. Try again."


def signal_locked():
    """Called by the locker once the screen is actually locked."""
    raw = os.environ.pop(SLEEP_LOCK_ENV, None)
    if raw is not None:
        # xss-lock: closing the inhibitor fd lets suspend proceed
        try:
            os.close(int(raw))
        except (ValueError, OSError) as e:
            logger.warning(f"Could not close {SLEEP_LOCK_ENV}={raw}: {e}")

    raw = os.environ.pop(READY_ENV, None)
    if raw is not None:
        try:
            fd = int(raw)
            try:
                os.write(fd, b"1")
            except BrokenPipeError:
                pass  # `lock -f` already returned (a respawned locker)
            os.close(fd)
        except (ValueError, OSError) as e:
            logger.warning(f"Could not signal {READY_ENV}={raw}: {e}")


def _wait_until_locked(ready_r: int) -> int:
    """Foreground half of -f: exit 0 once the background locker is locked."""
    readable, _, _ = select.select([ready_r], [], [], READY_TIMEOUT_S)
    if not readable:
        logger.error(f"Screen not locked after {READY_TIMEOUT_S}s")
        return EXIT_LOCK_FAILED
    # EOF without the byte: the background supervisor gave up before locking
    return 0 if os.read(ready_r, 1) == b"1" else EXIT_LOCK_FAILED


def supervise(daemonize: bool = False) -> int:
    instance = _acquire_single_instance()
    if instance is None:
        logger.info("Lock screen already running")
        return EXIT_ALREADY_RUNNING

    logger.info("Starting the lock screen")
    ready_fd = None
    if daemonize:
        ready_r, ready_w = os.pipe()
        if os.fork() > 0:
            # the flock stays held by the background copy of this file
            os.close(ready_w)
            instance.close()
            return _wait_until_locked(ready_r)
        os.close(ready_r)
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
        os.close(devnull)
        ready_fd = ready_w

    try:
        return _supervise_lockers(ready_fd)
    finally:
        # if we never locked, this EOF tells the foreground -f process
        if ready_fd is not None:
            os.close(ready_fd)


def _supervise_lockers(ready_fd: int | None) -> int:
    sleep_fd = _take_sleep_lock_fd()
    crashes: list[float] = []

    while True:
        env = os.environ.copy()
        pass_fds: list[int] = []
        if sleep_fd is not None:
            pass_fds.append(sleep_fd)
        else:
            env.pop(SLEEP_LOCK_ENV, None)
        # unlike the sleep fd we keep our copy, so a respawned locker can
        # still report "locked" if the first one crashed before locking
        if ready_fd is not None:
            pass_fds.append(ready_fd)
            env[READY_ENV] = str(ready_fd)
        else:
            env.pop(READY_ENV, None)

        proc = subprocess.Popen(
            [sys.executable, "-m", "lock", "--child"],
            cwd=ROOT_DIR,
            env=env,
            pass_fds=pass_fds,
        )

        # only the child may hold the inhibitor fd: it closes it once the
        # grabs succeed. If we kept a copy, suspend would never proceed.
        if sleep_fd is not None:
            os.close(sleep_fd)
            sleep_fd = None

        code = proc.wait()

        if code == EXIT_UNLOCKED:
            return EXIT_UNLOCKED

        if code == EXIT_ALREADY_RUNNING:
            return code

        if code == EXIT_LOCK_FAILED:
            logger.error("Locker could not lock the screen; screen NOT locked")
            _notify("Screen not locked", _lock_failed_reason())
            return code

        # anything else is a crash (exception => 1, signal => negative)
        now = time.monotonic()
        crashes = [t for t in crashes if now - t < CRASH_WINDOW_S] + [now]
        logger.error(f"Locker exited unexpectedly (code {code}); crash #{len(crashes)}")

        if len(crashes) >= MAX_CRASHES:
            return _fallback_locker()
