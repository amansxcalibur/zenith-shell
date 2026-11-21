import glob
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from installer.paths import VENDOR_DIR
from installer.system import have, run, unreachable
from installer.wm import WM_FEATURE


@dataclass
class Tool:
    """Not a distro package, so built from source."""

    name: str
    cmd: str  # installed if it's on PATH, "" for libraries
    feature: str = "core"
    requires: tuple[str, ...] = ()  # build commands, checked in pre-flight
    build: str = ""  # the backend method that builds it
    hosts: tuple[str, ...] = ()  # extra URLs that must be reachable
    files: tuple[str, ...] = ()  # globs that prove a library is installed

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

    # provided by the distro backends
    def missing_pkgs(self, pkgs: list[str]) -> list[str]:
        raise NotImplementedError

    def check_packages(self, missing: list[str]) -> list[Problem]:
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

    def plan_notes(self, plan: Plan) -> list[str]:
        return []

    def uninstall_tools(self, names: list[str]) -> None:
        """Remove tools that were built from source."""

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

        # build prerequisites (cargo, go...); only demanded when the tool is actually missing
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

        if plan.missing_pkgs:
            problems += self.check_packages(plan.missing_pkgs)
        return problems

    def vendor(self, name: str, url: str) -> Path:
        """Clone (or fast-forward) a source tree into the vendors directory."""
        path = VENDOR_DIR / name
        if (path / ".git").is_dir():
            run(
                ["git", "-C", path, "pull", "--ff-only", "--quiet"],
                label=f"Updating {name}",
                check=False,  # offline or diverged: build what we already have
            )
        else:
            VENDOR_DIR.mkdir(parents=True, exist_ok=True)
            run(["git", "clone", "--depth=1", url, path], label=f"Cloning {name}")
        return path

    def build_meson(
        self,
        name: str,
        url: str,
        *setup_args: str,
        post_install: Callable[[], None] | None = None,
    ) -> None:
        """Clone, configure, compile as the user, install as root."""
        path = self.vendor(name, url)
        cmd = ["meson", "setup", "build", "--prefix=/usr", *setup_args]
        if (path / "build").exists():
            cmd.append("--reconfigure")
        run(cmd, cwd=path, label=f"Configuring {name}")
        run(["ninja", "-C", "build"], cwd=path, label=f"Building {name}")
        run(
            ["meson", "install", "-C", "build", "--no-rebuild"],
            sudo=True,
            cwd=path,
            label=f"Installing {name}",
        )
        if post_install:
            post_install()

    def uninstall_meson(self, name: str) -> None:
        build = VENDOR_DIR / name / "build"
        if build.is_dir():
            run(
                ["ninja", "-C", build, "uninstall"],
                sudo=True,
                check=False,
                label=f"Removing {name}",
            )
