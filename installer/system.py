import collections
import concurrent.futures
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from installer.paths import INSTALL_DIR, LOG_FILE, SHELL_PROCESS, VENV_DIR
from installer.ui import CYAN, DIM, NC, OPTS, SPINNER, TTY, fmt_time, info, mark, vlen


class InstallError(Exception):
    pass


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def capture(cmd, **kwargs) -> tuple[int, str]:
    """Run quietly, return (returncode, stdout). 127 if the binary is missing."""
    try:
        proc = subprocess.run(
            [str(part) for part in cmd],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            **kwargs,
        )
        return proc.returncode, proc.stdout
    except FileNotFoundError:
        return 127, ""


def git_out(*args: str, strip: bool = True) -> str:
    rc, out = capture(["git", "-C", str(INSTALL_DIR), *args])
    if rc != 0:
        return ""
    return out.strip() if strip else out.rstrip("\n")


def shell_running() -> bool:
    return capture(["pgrep", "-f", SHELL_PROCESS])[0] == 0


def stop_shell() -> bool:
    return capture(["pkill", "-f", SHELL_PROCESS])[0] == 0


def venv_ok() -> bool:
    """False if the virtualenv is missing or its interpreter no longer works,
    e.g. after a Python upgrade removed the version it was created with."""
    return capture([VENV_DIR / "bin" / "python", "-c", "import pip"])[0] == 0


def run(
    cmd,
    *,
    label: str | None = None,
    sudo: bool = False,
    cwd=None,
    env=None,
    check: bool = True,
) -> int:
    """Run a command with a live one-line status; full output goes to LOG_FILE."""
    cmd = [str(part) for part in cmd]
    if sudo and os.geteuid() != 0:
        # -n: never prompt mid-install, ensure_sudo() cached the credentials
        cmd = ["sudo", "-n", *cmd]
    label = label or " ".join(cmd[:4])
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tail: collections.deque[str] = collections.deque(maxlen=15)
    last = [""]
    start = time.time()

    with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            raise InstallError(f"Command not found: {cmd[0]}") from None

        def pump() -> None:
            try:
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    tail.append(line.rstrip())
                    if line.strip():
                        last[0] = line.strip()
                    if OPTS.verbose:
                        print(f"    {DIM}{line.rstrip()}{NC}", flush=True)
            # the log closed: we gave up waiting (Ctrl-C, or a daemon kept the pipe)
            except ValueError:
                pass

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        frame = 0
        try:
            while proc.poll() is None:
                if TTY and not OPTS.verbose:
                    cols = shutil.get_terminal_size((80, 20)).columns
                    prefix = f"  {CYAN}{SPINNER[frame % len(SPINNER)]}{NC} {label} "
                    room = max(0, cols - vlen(prefix) - 2)
                    print(
                        f"\r\033[K{prefix}{DIM}{last[0][:room]}{NC}", end="", flush=True
                    )
                frame += 1
                time.sleep(0.1)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader.join(timeout=2)
            if TTY:
                print("\r\033[K", end="")
            raise
        reader.join(timeout=2)

    rc = proc.returncode
    took = fmt_time(time.time() - start)
    clear = "\r\033[K" if TTY else ""
    print(f"{clear}  {mark(rc == 0)} {label} {DIM}({took}){NC}")
    if rc != 0:
        for line in list(tail)[-10:]:
            print(f"    {DIM}{line[:200]}{NC}")
        if check:
            raise InstallError(f"{label} failed (exit {rc}). Full log: {LOG_FILE}")
    return rc


_sudo_started = False


def ensure_sudo() -> None:
    global _sudo_started
    if os.geteuid() == 0 or _sudo_started:
        return
    if not have("sudo"):
        raise InstallError("sudo is required but not installed.")
    cached = subprocess.run(
        ["sudo", "-n", "true"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if cached.returncode != 0:
        info("Root privileges are needed.")
        if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
            raise InstallError("sudo authentication failed.")

    def keepalive() -> None:
        while True:
            time.sleep(50)
            subprocess.run(
                ["sudo", "-n", "-v"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    threading.Thread(target=keepalive, daemon=True).start()
    _sudo_started = True


def download(url: str, dest: Path, retries: int = 3) -> None:
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, retries + 1):
        try:
            with (
                urllib.request.urlopen(url, timeout=30) as response,
                open(tmp, "wb") as out,
            ):
                shutil.copyfileobj(response, out)
            tmp.replace(dest)
            return
        except Exception as exc:
            if attempt == retries:
                raise InstallError(f"Download failed: {url} ({exc})") from exc
            time.sleep(2 * attempt)


def responds(url: str, timeout: int = 15) -> bool:
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, method="HEAD"), timeout=timeout
        )
    except urllib.error.HTTPError:
        return True  # server answered -> reachable
    except Exception:
        return False
    return True


def unreachable(urls: list[str]) -> list[str]:
    def probe(url: str) -> str | None:
        # one slow TLS handshake must not stop an install
        return None if responds(url) or responds(url) else url

    if not urls:
        return []
    with concurrent.futures.ThreadPoolExecutor(len(urls)) as pool:
        return [url for url in pool.map(probe, urls) if url]


def detect_distro() -> str:
    try:
        text = Path("/etc/os-release").read_text()
    except OSError:
        raise InstallError("Cannot read /etc/os-release.") from None
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    words = f"{fields.get('ID', '')} {fields.get('ID_LIKE', '')}".translate(
        str.maketrans("", "", "\"'")
    ).split()
    if "arch" in words:
        return "arch"
    if "ubuntu" in words or "debian" in words:
        return "ubuntu"
    raise InstallError(
        f"Unsupported distro ({' '.join(words)}). Supported: Arch-based, Ubuntu/Debian-based."
    )
