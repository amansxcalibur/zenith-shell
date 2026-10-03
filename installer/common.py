import collections
import concurrent.futures
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace


SHELL_NAME = "zenith-shell"
REPO_URL = "https://github.com/amansxcalibur/zenith-shell.git"

HOME = Path.home()
INSTALL_DIR = Path(os.environ.get("ZENITH_DIR", HOME / ".config" / SHELL_NAME))
VENV_DIR = INSTALL_DIR / ".venv"
VENDOR_DIR = INSTALL_DIR / "vendors"
BIN_DIR = HOME / ".local" / "bin"
CARGO_BIN = HOME / ".cargo" / "bin"
STATE_FILE = (
    Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state"))
    / SHELL_NAME
    / "install.json"
)
LOG_FILE = (
    Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / SHELL_NAME / "install.log"
)
# where `uninstall` keeps your settings if you ask it to (restored on the next fresh install)
BACKUP_DIR = HOME / ".config" / f"{SHELL_NAME}-backup"
# the running shell renames itself with setproctitle(SHELL_NAME + "-shell") in main.py
SHELL_TITLE = f"{SHELL_NAME}-shell"

# Remember the PATH the user actually has (for the "add ~/.local/bin" notice),
# then extend ours so freshly installed tools (cargo, matugen) are found.
ORIGINAL_PATH = os.environ.get("PATH", "")
for _p in (CARGO_BIN, BIN_DIR):
    if str(_p) not in ORIGINAL_PATH.split(":"):
        os.environ["PATH"] = f"{_p}:{os.environ['PATH']}"

# window manager -> feature set of dependencies it needs
WM_FEATURE = {"i3": "x11", "sway": "wayland"}

OPTS = SimpleNamespace(yes=False, dry_run=False)


class InstallError(Exception):
    pass


TTY = sys.stdout.isatty()
COLOR = TTY and "NO_COLOR" not in os.environ
UTF = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()


def _c(code: str) -> str:
    return f"\033[{code}m" if COLOR else ""


RED, GREEN, YELLOW = _c("0;31"), _c("0;32"), _c("1;33")
BLUE, CYAN, DIM, BOLD, NC = _c("0;34"), _c("0;36"), _c("2"), _c("1"), _c("0")

SYM = {
    "ok": "✔" if UTF else "OK",
    "err": "✖" if UTF else "X",
    "warn": "⚠" if UTF else "!",
    "dot": "•" if UTF else "*",
}
BOX = ("╭", "╮", "╰", "╯", "─", "│") if UTF else ("+", "+", "+", "+", "-", "|")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if UTF else "|/-\\"
_ANSI = re.compile(r"\033\[[0-9;]*m")
_LEADING_ANSI = re.compile(r"^(?:\033\[[0-9;]*m)*")

_step = {"n": 0, "total": 0}


def vlen(text: str) -> int:
    """Visible length (ANSI colour codes don't count)."""
    return len(_ANSI.sub("", text))


def mark(good: bool) -> str:
    return f"{GREEN}{SYM['ok']}{NC}" if good else f"{RED}{SYM['err']}{NC}"


def info(msg: str) -> None:
    print(f"{BLUE}{BOLD}::{NC} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}{BOLD}[{SYM['ok']}]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}{BOLD}{SYM['warn']}{NC} {msg}")


def err(msg: str) -> None:
    print(f"{RED}{BOLD}{SYM['err']}{NC} {msg}")


def set_total(n: int) -> None:
    _step["n"], _step["total"] = 0, n


def step(title: str) -> None:
    _step["n"] += 1
    print(f"\n{CYAN}{BOLD}[{_step['n']}/{_step['total']}]{NC} {BOLD}{title}{NC}")


def fmt_time(sec: float) -> str:
    minutes, seconds = divmod(int(sec), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


def wrap_line(line: str, width: int) -> list[str]:
    """Word-wrap one (possibly coloured) line to `width` visible columns.

    Continuation lines keep the original indentation (+2 after a bullet/status mark),
    and the line's colour is re-applied to every wrapped piece.
    """
    if vlen(line) <= width:
        return [line]
    lead = _LEADING_ANSI.match(line).group(0)
    body = line[len(lead) :]
    indent = len(body) - len(body.lstrip(" "))
    tokens = _ANSI.sub("", body).split()
    hang = indent + (
        2 if tokens and len(tokens[0]) == 1 and not tokens[0].isalnum() else 0
    )

    limit = max(10, width - hang)
    words: list[str] = []
    for word in body.split():
        if "\033" not in word and len(word) > limit:  # absurdly long token (e.g. URL)
            words += [word[i : i + limit] for i in range(0, len(word), limit)]
        else:
            words.append(word)

    rows: list[str] = []
    cur, cur_len, cur_indent = "", 0, indent
    for word in words:
        gap = 1 if cur else 0
        if cur and cur_indent + cur_len + gap + vlen(word) > width:
            rows.append(" " * cur_indent + cur)
            cur, cur_len, cur_indent = word, vlen(word), hang
        else:
            cur = f"{cur} {word}" if cur else word
            cur_len += gap + vlen(word)
    rows.append(" " * cur_indent + cur)

    if lead:
        rows = [
            f"{lead}{row}" if row.endswith(NC) else f"{lead}{row}{NC}" for row in rows
        ]
    return rows


def panel(title: str, lines: list[str], color: str = "") -> None:
    color = color or BLUE
    tl, tr, bl, br, h, v = BOX
    limit = max(shutil.get_terminal_size((80, 20)).columns - 4, 40)
    rows = [piece for line in lines for piece in wrap_line(line, limit)]
    width = max([vlen(row) for row in rows] + [vlen(title) + 1, 38])
    inner = width + 2
    dashes = h * (inner - vlen(title) - 3)
    print(f"{color}{tl}{h} {BOLD}{title}{NC}{color} {dashes}{tr}{NC}")
    for row in rows:
        pad = " " * (width - vlen(row))
        print(f"{color}{v}{NC} {row}{pad} {color}{v}{NC}")
    print(f"{color}{bl}{h * inner}{br}{NC}")


def confirm(question: str, default: bool = True) -> bool:
    if OPTS.yes:
        return True
    if not sys.stdin.isatty():
        return False
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = (
            input(f"{BLUE}{BOLD}?{NC} {question} {DIM}{suffix}{NC} ").strip().lower()
        )
    except EOFError:
        return False
    return default if not answer else answer.startswith("y")


def choose(question: str, options: list[str]) -> str | None:
    if not sys.stdin.isatty():
        return None
    print(f"{BLUE}{BOLD}?{NC} {question}")
    for i, option in enumerate(options, 1):
        print(f"   {i}) {option}")
    try:
        raw = input("   > ").strip()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw if raw in options else None


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


def shell_running() -> bool:
    return capture(["pgrep", "-f", f"^{SHELL_TITLE}"])[0] == 0


def stop_shell() -> bool:
    return capture(["pkill", "-f", f"^{SHELL_TITLE}"])[0] == 0


def notify(summary: str, body: str = "") -> None:
    if (
        have("notify-send")
        and capture(["notify-send", "-a", "Zenith Shell", summary, body])[0] == 0
    ):
        return
    print(f"{summary}: {body}", file=sys.stderr)


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
        cmd = [
            "sudo",
            "-n",
            *cmd,
        ]  # -n: never prompt mid-install (creds are cached by ensure_sudo)
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
            for line in proc.stdout:
                log.write(line)
                log.flush()
                tail.append(line.rstrip())
                if line.strip():
                    last[0] = line.strip()

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        frame = 0
        try:
            while proc.poll() is None:
                if TTY:
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
        info("Administrator rights are needed – asking once, up front.")
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


def unreachable(urls: list[str]) -> list[str]:
    def probe(url: str) -> str | None:
        try:
            urllib.request.urlopen(
                urllib.request.Request(url, method="HEAD"), timeout=6
            )
        except urllib.error.HTTPError:
            return None  # server answered -> reachable
        except Exception:
            return url
        return None

    if not urls:
        return []
    with concurrent.futures.ThreadPoolExecutor(len(urls)) as pool:
        return [url for url in pool.map(probe, urls) if url]


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(
    wms: list[str],
    distro: str,
    packages: list[str] | None = None,
    tools: list[str] | None = None,
) -> None:
    """Merge into the state file. Nothing is ever 'forgotten' automatically."""
    state = load_state()
    state["wms"] = sorted(set(state.get("wms", [])) | set(wms))
    state["packages"] = sorted(set(state.get("packages", [])) | set(packages or []))
    state["tools"] = sorted(set(state.get("tools", [])) | set(tools or []))
    state["distro"] = distro
    state["updated"] = datetime.datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def update_state(**fields) -> None:
    """Set (or, with None, remove) individual keys in the state file."""
    state = load_state()
    for key, value in fields.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def current_wm() -> str | None:
    desktop = f"{os.environ.get('XDG_CURRENT_DESKTOP', '')} {os.environ.get('DESKTOP_SESSION', '')}".lower()
    if os.environ.get("SWAYSOCK") or "sway" in desktop:
        return "sway"
    if os.environ.get("I3SOCK") or re.search(r"\bi3\b", desktop):
        return "i3"
    return None


def resolve_wms(choice: str, interactive: bool = True) -> list[str]:
    """--wm explicit > (previously installed + current session) > WMs found on PATH > ask."""
    if choice == "both":
        return ["i3", "sway"]
    if choice in WM_FEATURE:
        return [choice]
    wms = list(load_state().get("wms", []))
    current = current_wm()
    if current and current not in wms:
        wms.append(current)
    if not wms:
        wms = [wm for wm in WM_FEATURE if have(wm)]
    if not wms and interactive:
        picked = choose(
            "Which window manager should Zenith be set up for?", ["i3", "sway", "both"]
        )
        if picked:
            wms = ["i3", "sway"] if picked == "both" else [picked]
    return sorted(set(wms), key=list(WM_FEATURE).index)


def detect_distro() -> str:
    try:
        text = Path("/etc/os-release").read_text()
    except OSError:
        raise InstallError("Cannot read /etc/os-release.") from None
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    words = f"{fields.get('ID', '')} {fields.get('ID_LIKE', '')}".replace(
        '"', ""
    ).split()
    if "arch" in words:
        return "arch"
    if "ubuntu" in words or "debian" in words:
        return "ubuntu"
    raise InstallError(
        f"Unsupported distro ({' '.join(words)}). Supported: Arch-based, Ubuntu/Debian-based."
    )


@dataclass
class Tool:
    """Something that is not a distro package and must be built (cargo, meson...)."""

    name: str
    cmd: str  # installed if this command is on PATH ('' if none)
    feature: str = "core"
    requires: tuple[
        str, ...
    ] = ()  # build prerequisites (commands) – checked in PRE-FLIGHT
    build: str = ""  # name of the backend method that builds it
    hosts: tuple[str, ...] = ()  # extra URLs that must be reachable
    files: tuple[
        str, ...
    ] = ()  # alternative probe: glob patterns (libraries without a command)

    def installed(self) -> bool:
        if self.cmd and have(self.cmd):
            return True
        return any(glob.glob(pattern) for pattern in self.files)


@dataclass
class Problem:
    msg: str
    hint: str = ""
    fix: Callable[[], None] | None = None
    fix_desc: str = ""


@dataclass
class Plan:
    wms: list[str]
    features: list[str]
    pkgs: list[str]
    missing_pkgs: list[str]
    tools: list[Tool] = field(default_factory=list)  # only the missing ones

    @property
    def needs_work(self) -> bool:
        return bool(self.missing_pkgs or self.tools)


class Backend:
    name = ""
    pretty = ""
    REMOVE_CMD = ""  # shown (never run) after uninstall
    PACKAGES: dict[str, list[str]] = {}  # noqa: RUF012
    TOOLS: list[Tool] = []  # noqa: RUF012
    VENV_SYSTEM_SITE = False

    # ---- to be provided by the distro modules -------------------------------
    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        raise NotImplementedError

    def check_packages(self, missing: list[str]) -> list[Problem]:
        """Verify every package we are about to install actually exists."""
        raise NotImplementedError

    def install_packages(self, plan: Plan) -> None:
        raise NotImplementedError

    def prepare(self) -> None:
        """Hook that runs (with sudo) before pre-flight, e.g. `apt update`."""

    def system_checks(self, plan: Plan) -> list[Problem]:
        return []

    def prereq_fixers(self) -> dict[str, tuple[str, Callable[[], None]]]:
        return {}

    def extra_hosts(self, plan: Plan) -> list[str]:
        return []

    def uninstall_tools(self, names: list[str]) -> None:
        """Remove tools that were built from source."""

    # ---- shared logic --------------------------------------------------------
    def plan(self, wms: list[str]) -> Plan:
        features = ["core", *(WM_FEATURE[wm] for wm in wms)]
        pkgs: list[str] = []
        for feature in features:
            for pkg in self.PACKAGES.get(feature, []):
                if pkg not in pkgs:
                    pkgs.append(pkg)
        tools = [t for t in self.TOOLS if t.feature in features and not t.installed()]
        return Plan(list(wms), features, pkgs, self.missing_pkgs(pkgs), tools)

    def install_tools(self, plan: Plan) -> None:
        for tool in plan.tools:
            getattr(self, tool.build)()

    def preflight(self, plan: Plan, command: str) -> list[Problem]:
        problems: list[Problem] = []
        if not sys.platform.startswith("linux"):
            problems.append(Problem("Not running on Linux."))
        if os.geteuid() == 0:
            problems.append(
                Problem(
                    "Running as root.",
                    "Run as your normal user; sudo is requested when needed.",
                )
            )
        if os.environ.get("VIRTUAL_ENV"):
            problems.append(
                Problem(
                    f"A Python virtualenv is active ({os.environ['VIRTUAL_ENV']}).",
                    "Run `deactivate` and start the installer again.",
                )
            )
        if plan.needs_work and os.geteuid() != 0 and not have("sudo"):
            problems.append(
                Problem(
                    "sudo is not installed.",
                    "Install sudo, or run the installer from a user that has it.",
                )
            )

        # build prerequisites (cargo, go...) – only demanded when the tool is actually missing
        fixers = self.prereq_fixers()
        seen: set[str] = set()
        for tool in plan.tools:
            for req in tool.requires:
                if have(req) or req in seen:
                    continue
                seen.add(req)
                desc, fix = fixers.get(req, ("", None))
                problems.append(
                    Problem(
                        f"`{req}` is needed to build {tool.name} but is not installed.",
                        "" if fix else "Install it and re-run.",
                        fix,
                        desc,
                    )
                )

        problems += self.system_checks(plan)

        # network
        hosts: list[str] = []
        if command in ("install", "update"):
            hosts.append("https://pypi.org")  # pip install -r requirements.txt
        if command == "install":
            hosts += ["https://github.com", "https://raw.githubusercontent.com"]
        elif plan.tools:
            hosts.append("https://github.com")
        hosts += self.extra_hosts(plan)
        for tool in plan.tools:
            hosts += list(tool.hosts)
        bad = unreachable(sorted(set(hosts)))
        if bad:
            problems.append(
                Problem(
                    f"Cannot reach: {', '.join(bad)}",
                    "Check your internet connection / proxy / DNS.",
                )
            )

        # do all packages exist on this system?
        if plan.missing_pkgs:
            problems += self.check_packages(plan.missing_pkgs)
        return problems
