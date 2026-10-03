"""Shared building blocks for the Zenith installer (stdlib only, Python 3.8+)."""
from __future__ import annotations

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
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

# ----------------------------------------------------------------------------
# Paths / constants
# ----------------------------------------------------------------------------
SHELL_NAME = "zenith-shell"
REPO_URL = "https://github.com/amansxcalibur/zenith-shell.git"

HOME = Path.home()
INSTALL_DIR = Path(os.environ.get("ZENITH_DIR", str(HOME / ".config" / SHELL_NAME)))
VENV_DIR = INSTALL_DIR / ".venv"
VENDOR_DIR = INSTALL_DIR / "vendors"
BIN_DIR = HOME / ".local" / "bin"
CARGO_BIN = HOME / ".cargo" / "bin"
STATE_FILE = Path(os.environ.get("XDG_STATE_HOME", str(HOME / ".local" / "state"))) / SHELL_NAME / "install.json"
LOG_FILE = Path(os.environ.get("XDG_CACHE_HOME", str(HOME / ".cache"))) / SHELL_NAME / "install.log"

# Remember the PATH the user actually has (for the "add ~/.local/bin" notice),
# then extend ours so freshly installed tools (cargo, matugen) are found.
ORIGINAL_PATH = os.environ.get("PATH", "")
for _p in (CARGO_BIN, BIN_DIR):
    if str(_p) not in os.environ["PATH"].split(":"):
        os.environ["PATH"] = "%s:%s" % (_p, os.environ["PATH"])

# window manager -> feature set of dependencies it needs
WM_FEATURE = {"i3": "x11", "sway": "wayland"}

OPTS = SimpleNamespace(yes=False, dry_run=False)


class InstallError(Exception):
    pass


# ----------------------------------------------------------------------------
# Terminal UI
# ----------------------------------------------------------------------------
TTY = sys.stdout.isatty()
COLOR = TTY and "NO_COLOR" not in os.environ
UTF = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()


def _c(code: str) -> str:
    return "\033[%sm" % code if COLOR else ""


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

_step = {"n": 0, "total": 0}


def vlen(s: str) -> int:
    return len(_ANSI.sub("", s))


def info(msg: str) -> None:
    print("%s%s::%s %s" % (BLUE, BOLD, NC, msg))


def ok(msg: str) -> None:
    print("%s%s[%s]%s %s" % (GREEN, BOLD, SYM["ok"], NC, msg))


def warn(msg: str) -> None:
    print("%s%s%s%s %s" % (YELLOW, BOLD, SYM["warn"], NC, msg))


def err(msg: str) -> None:
    print("%s%s%s%s %s" % (RED, BOLD, SYM["err"], NC, msg))


def set_total(n: int) -> None:
    _step["n"], _step["total"] = 0, n


def step(title: str) -> None:
    _step["n"] += 1
    print("\n%s%s[%d/%d]%s %s%s%s" % (CYAN, BOLD, _step["n"], _step["total"], NC, BOLD, title, NC))


def fmt_time(sec: float) -> str:
    sec = int(sec)
    return "%dm%02ds" % (sec // 60, sec % 60) if sec >= 60 else "%ds" % sec


def panel(title: str, lines: List[str], color: str = "") -> None:
    color = color or BLUE
    tl, tr, bl, br, h, v = BOX
    width = max([vlen(x) for x in lines] + [vlen(title) + 1, 38])
    inner = width + 2
    print("%s%s%s %s%s%s%s %s%s%s" % (color, tl, h, BOLD, title, NC, color, h * (inner - vlen(title) - 3), tr, NC))
    for line in lines:
        print("%s%s%s %s%s %s%s%s" % (color, v, NC, line, " " * (width - vlen(line)), color, v, NC))
    print("%s%s%s%s%s" % (color, bl, h * inner, br, NC))


def confirm(question: str, default: bool = True) -> bool:
    if OPTS.yes:
        return True
    if not sys.stdin.isatty():
        return False
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input("%s%s?%s %s %s%s%s " % (BLUE, BOLD, NC, question, DIM, suffix, NC)).strip().lower()
    except EOFError:
        return False
    return default if not answer else answer.startswith("y")


def choose(question: str, options: List[str]) -> Optional[str]:
    if not sys.stdin.isatty():
        return None
    print("%s%s?%s %s" % (BLUE, BOLD, NC, question))
    for i, o in enumerate(options, 1):
        print("   %d) %s" % (i, o))
    try:
        raw = input("   > ").strip()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw if raw in options else None


# ----------------------------------------------------------------------------
# Running commands (spinner + log file)
# ----------------------------------------------------------------------------
def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def capture(cmd, **kw):
    """Run quietly, return (returncode, stdout). 127 if the binary is missing."""
    try:
        p = subprocess.run([str(c) for c in cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True, errors="replace", **kw)
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, ""


def run(cmd, *, label: Optional[str] = None, sudo: bool = False, cwd=None, env=None, check: bool = True) -> int:
    """Run a command with a live one-line status; full output goes to LOG_FILE."""
    cmd = [str(c) for c in cmd]
    if sudo and os.geteuid() != 0:
        cmd = ["sudo", "-n"] + cmd  # -n: never prompt mid-install (creds are cached by ensure_sudo)
    label = label or " ".join(cmd[:4])
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tail = collections.deque(maxlen=15)
    last = [""]
    start = time.time()

    with open(str(LOG_FILE), "a", encoding="utf-8", errors="replace") as log:
        log.write("\n$ %s\n" % " ".join(cmd))
        log.flush()
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True, errors="replace", bufsize=1)
        except FileNotFoundError:
            raise InstallError("Command not found: %s" % cmd[0])

        def pump():
            for line in proc.stdout:
                log.write(line)
                log.flush()
                tail.append(line.rstrip())
                if line.strip():
                    last[0] = line.strip()

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        i = 0
        try:
            while proc.poll() is None:
                if TTY:
                    cols = shutil.get_terminal_size((80, 20)).columns
                    prefix = "  %s%s%s %s " % (CYAN, SPINNER[i % len(SPINNER)], NC, label)
                    room = max(0, cols - vlen(prefix) - 2)
                    print("\r\033[K%s%s%s%s" % (prefix, DIM, last[0][:room], NC), end="", flush=True)
                i += 1
                time.sleep(0.1)
        except KeyboardInterrupt:
            proc.terminate()
            if TTY:
                print("\r\033[K", end="")
            raise
        reader.join(timeout=2)

    rc = proc.returncode
    took = fmt_time(time.time() - start)
    mark = "%s%s%s" % (GREEN, SYM["ok"], NC) if rc == 0 else "%s%s%s" % (RED, SYM["err"], NC)
    print("%s  %s %s %s(%s)%s" % ("\r\033[K" if TTY else "", mark, label, DIM, took, NC))
    if rc != 0:
        for line in list(tail)[-10:]:
            print("    %s%s%s" % (DIM, line[:200], NC))
        if check:
            raise InstallError("%s failed (exit %d). Full log: %s" % (label, rc, LOG_FILE))
    return rc


_sudo_started = False


def ensure_sudo() -> None:
    """Ask for the sudo password ONCE, up front, and keep the ticket alive."""
    global _sudo_started
    if os.geteuid() == 0 or _sudo_started:
        return
    if not have("sudo"):
        raise InstallError("sudo is required but not installed.")
    if subprocess.run(["sudo", "-n", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        info("Administrator rights are needed – asking once, up front.")
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            raise InstallError("sudo authentication failed.")

    def keepalive():
        while True:
            time.sleep(50)
            subprocess.run(["sudo", "-n", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    threading.Thread(target=keepalive, daemon=True).start()
    _sudo_started = True


def download(url: str, dest: Path, retries: int = 3) -> None:
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r, open(str(tmp), "wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(dest)
            return
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                raise InstallError("Download failed: %s (%s)" % (url, e))
            time.sleep(2 * attempt)


def unreachable(urls: List[str]) -> List[str]:
    def probe(u: str) -> Optional[str]:
        try:
            urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=6)
        except urllib.error.HTTPError:
            return None  # server answered -> reachable
        except Exception:  # noqa: BLE001
            return u
        return None

    if not urls:
        return []
    with concurrent.futures.ThreadPoolExecutor(len(urls)) as ex:
        return [u for u in ex.map(probe, urls) if u]


# ----------------------------------------------------------------------------
# State + window-manager detection
# ----------------------------------------------------------------------------
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_state(wms: List[str], distro: str) -> None:
    st = load_state()
    st["wms"] = sorted(set(st.get("wms", [])) | set(wms))  # never "forget" a WM automatically
    st["distro"] = distro
    st["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2))


def current_wm() -> Optional[str]:
    desk = (os.environ.get("XDG_CURRENT_DESKTOP", "") + " " + os.environ.get("DESKTOP_SESSION", "")).lower()
    if os.environ.get("SWAYSOCK") or "sway" in desk:
        return "sway"
    if os.environ.get("I3SOCK") or re.search(r"\bi3\b", desk):
        return "i3"
    return None


def resolve_wms(choice: str, interactive: bool = True) -> List[str]:
    """--wm explicit > (previously installed + current session) > WMs found on PATH > ask."""
    if choice == "both":
        return ["i3", "sway"]
    if choice in WM_FEATURE:
        return [choice]
    wms = list(load_state().get("wms", []))
    cur = current_wm()
    if cur and cur not in wms:
        wms.append(cur)
    if not wms:
        wms = [w for w in WM_FEATURE if have(w)]
    if not wms and interactive:
        pick = choose("Which window manager should Zenith be set up for?", ["i3", "sway", "both"])
        if pick:
            wms = ["i3", "sway"] if pick == "both" else [pick]
    return sorted(set(wms), key=list(WM_FEATURE).index)


def detect_distro() -> str:
    try:
        text = Path("/etc/os-release").read_text()
    except OSError:
        raise InstallError("Cannot read /etc/os-release.")
    fields = dict(l.split("=", 1) for l in text.splitlines() if "=" in l)
    words = (fields.get("ID", "") + " " + fields.get("ID_LIKE", "")).replace('"', "").split()
    if "arch" in words:
        return "arch"
    if "ubuntu" in words or "debian" in words:
        return "ubuntu"
    raise InstallError("Unsupported distro (%s). Supported: Arch-based, Ubuntu/Debian-based." % " ".join(words))


# ----------------------------------------------------------------------------
# Dependency model + backend base class (this is the "resolver")
# ----------------------------------------------------------------------------
@dataclass
class Tool:
    """Something that is not a distro package and must be built (cargo, meson...)."""
    name: str
    cmd: str                       # probe: tool counts as installed if this is on PATH ('' if none)
    feature: str = "core"
    requires: tuple = ()           # build prerequisites (commands) – checked in PRE-FLIGHT
    build: str = ""                # name of the backend method that builds it
    hosts: tuple = ()              # extra URLs that must be reachable
    files: tuple = ()              # alternative probe: glob patterns (for libraries without a command)

    def installed(self) -> bool:
        if self.cmd and have(self.cmd):
            return True
        return any(glob.glob(pat) for pat in self.files)


@dataclass
class Problem:
    msg: str
    hint: str = ""
    fix: Optional[Callable[[], None]] = None
    fix_desc: str = ""


@dataclass
class Plan:
    wms: List[str]
    features: List[str]
    pkgs: List[str]
    missing_pkgs: List[str]
    tools: List[Tool] = field(default_factory=list)  # only the missing ones

    @property
    def needs_work(self) -> bool:
        return bool(self.missing_pkgs or self.tools)


class Backend:
    name = ""
    pretty = ""
    PACKAGES: Dict[str, List[str]] = {}
    TOOLS: List[Tool] = []
    VENV_SYSTEM_SITE = False

    # ---- to be provided by the distro modules -------------------------------
    def missing_pkgs(self, pkgs: List[str]) -> List[str]:
        raise NotImplementedError

    def check_packages(self, missing: List[str]) -> List[Problem]:
        """Verify every package we are about to install actually exists."""
        raise NotImplementedError

    def install_packages(self, plan: Plan) -> None:
        raise NotImplementedError

    def prepare(self) -> None:
        """Hook that runs (with sudo) before pre-flight, e.g. `apt update`."""

    def system_checks(self, plan: Plan) -> List[Problem]:
        return []

    def prereq_fixers(self) -> Dict[str, tuple]:
        return {}

    def extra_hosts(self, plan: Plan) -> List[str]:
        return []

    # ---- shared logic --------------------------------------------------------
    def plan(self, wms: List[str]) -> Plan:
        features = ["core"] + [WM_FEATURE[w] for w in wms]
        pkgs: List[str] = []
        for f in features:
            for p in self.PACKAGES.get(f, []):
                if p not in pkgs:
                    pkgs.append(p)
        tools = [t for t in self.TOOLS if t.feature in features and not t.installed()]
        return Plan(list(wms), features, pkgs, self.missing_pkgs(pkgs), tools)

    def install_tools(self, plan: Plan) -> None:
        for t in plan.tools:
            getattr(self, t.build)()

    def preflight(self, plan: Plan, command: str) -> List[Problem]:
        P: List[Problem] = []
        if not sys.platform.startswith("linux"):
            P.append(Problem("Not running on Linux."))
        if os.geteuid() == 0:
            P.append(Problem("Running as root.", "Run as your normal user; sudo is requested when needed."))
        if sys.version_info < (3, 8):
            P.append(Problem("Python 3.8+ required.", "Found %s." % sys.version.split()[0]))
        if os.environ.get("VIRTUAL_ENV"):
            P.append(Problem("A Python virtualenv is active (%s)." % os.environ["VIRTUAL_ENV"],
                             "Run `deactivate` and start the installer again."))
        if plan.needs_work and os.geteuid() != 0 and not have("sudo"):
            P.append(Problem("sudo is not installed.", "Install sudo, or run the installer from a user that has it."))

        # build prerequisites (cargo, go...) – only demanded when the tool is actually missing
        fixers = self.prereq_fixers()
        seen = set()
        for t in plan.tools:
            for req in t.requires:
                if have(req) or req in seen:
                    continue
                seen.add(req)
                desc, fn = fixers.get(req, ("", None))
                P.append(Problem("`%s` is needed to build %s but is not installed." % (req, t.name),
                                 "Install it and re-run." if not fn else "", fn, desc))

        P += self.system_checks(plan)

        # network
        hosts: List[str] = []
        if command == "install":
            hosts += ["https://github.com", "https://raw.githubusercontent.com"]
        elif plan.tools:
            hosts += ["https://github.com"]
        hosts += self.extra_hosts(plan)
        for t in plan.tools:
            hosts += list(t.hosts)
        bad = unreachable(sorted(set(hosts)))
        if bad:
            P.append(Problem("Cannot reach: " + ", ".join(bad), "Check your internet connection / proxy / DNS."))

        # do all packages exist on this system?
        if plan.missing_pkgs:
            P += self.check_packages(plan.missing_pkgs)
        return P