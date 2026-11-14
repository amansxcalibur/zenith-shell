import argparse
import collections
import difflib
import os
import re
import shutil
import sys
import time
from pathlib import Path

INSTALLER_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(INSTALLER_DIR), str(INSTALLER_DIR.parent)]

import common as c
from config.wm_conflicts import find_wm_conflicts
from common import (
    BLUE,
    BOLD,
    DIM,
    GREEN,
    NC,
    RED,
    SYM,
    YELLOW,
    InstallError,
    info,
    mark,
    ok,
    panel,
    run,
    warn,
)

LOGO = r"""
 /$$$$$$$$ /$$$$$$$$ /$$   /$$ /$$$$$$ /$$$$$$$$ /$$   /$$
|_____ $$ | $$_____/| $$$ | $$|_  $$_/|__  $$__/| $$  | $$
     /$$/ | $$      | $$$$| $$  | $$     | $$   | $$  | $$
    /$$/  | $$$$$   | $$ $$ $$  | $$     | $$   | $$$$$$$$
   /$$/   | $$__/   | $$  $$$$  | $$     | $$   | $$__  $$
  /$$/    | $$      | $$\  $$$  | $$     | $$   | $$  | $$
 /$$$$$$$$| $$$$$$$$| $$ \  $$ /$$$$$$   | $$   | $$  | $$
|________/|________/|__/  \__/|______/   |__/   |__/  |__/
"""

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", c.HOME / ".local" / "share"))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", c.HOME / ".config"))
ZSH_COMPLETION_DIR = DATA_HOME / "zsh" / "site-functions"
# shell -> (file in installer/completions, where that shell loads it from)
COMPLETIONS = {
    "bash": (
        "zenith-shell.bash",
        DATA_HOME / "bash-completion" / "completions" / c.SHELL_NAME,
    ),
    "zsh": ("_zenith-shell", ZSH_COMPLETION_DIR / f"_{c.SHELL_NAME}"),
    "fish": (
        "zenith-shell.fish",
        CONFIG_HOME / "fish" / "completions" / f"{c.SHELL_NAME}.fish",
    ),
}

FONT_DIR = c.HOME / ".local" / "share" / "fonts" / c.SHELL_NAME
FONTS = {
    "RobotoFlex.ttf": "https://raw.githubusercontent.com/googlefonts/roboto-flex/main/fonts/RobotoFlex%5BGRAD%2CXOPQ%2CXTRA%2CYOPQ%2CYTAS%2CYTDE%2CYTFI%2CYTLC%2CYTUC%2Copsz%2Cslnt%2Cwdth%2Cwght%5D.ttf",
    "GoogleSansFlex.ttf": "https://raw.githubusercontent.com/amansxcalibur/zenith-resources/gh-pages/fonts/Google_Sans_Flex/GoogleSansFlex-VariableFont_GRAD%2CROND%2Copsz%2Cslnt%2Cwdth%2Cwght.ttf",
    "MaterialSymbolsRounded.ttf": "https://raw.githubusercontent.com/google/material-design-icons/master/variablefont/MaterialSymbolsRounded%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf",
}


def load_backend(name: str):
    if name == "arch":
        from arch import ArchBackend

        return ArchBackend()
    from ubuntu import UbuntuBackend

    return UbuntuBackend()


# ----------------------------------------------------------------------------
# Install steps
# ----------------------------------------------------------------------------
def step_python_env(backend, upgrade_pip: bool = True) -> None:
    py = c.VENV_DIR / "bin" / "python"
    exists = c.VENV_DIR.exists()
    if not exists or not c.venv_ok():
        # We may be running from this very venv, so build from its base interpreter.
        base = getattr(sys, "_base_executable", sys.executable)
        cmd = [base, "-m", "venv"]
        if exists:
            warn("The virtual environment is broken, rebuilding it.")
            cmd.append("--clear")
        if backend.VENV_SYSTEM_SITE:
            cmd.append("--system-site-packages")  # see python-gobject from pacman
        run([*cmd, c.VENV_DIR], label="Creating virtual environment")
    if upgrade_pip:
        run([py, "-m", "pip", "install", "--upgrade", "pip"], label="Upgrading pip")
    requirements = c.INSTALL_DIR / "requirements.txt"
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
    rc, out = c.capture([py, "-c", code, name])
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
        c.download(url, FONT_DIR / name)
    if fetched:
        run(["fc-cache", "-f"], label="Updating font cache")
    else:
        ok("Fonts present.")


LAUNCHER = r"""#!/usr/bin/env bash
cd "@INSTALL_DIR@" || exit 1

PROCESS='@PROCESS@'
COMMANDS=(start stop restart status lock settings setup help)

running() { pgrep -f "$PROCESS" >/dev/null; }

start_shell() {
    if running; then
        echo "zenith-shell is already running (use: zenith-shell restart)"
        return 0
    fi
    "@VENV@/bin/python" main.py &
    disown
}

stop_shell() {
    pkill -f "$PROCESS" || return 1
    for _ in {1..50}; do
        running || return 0
        sleep 0.1
    done
    pkill -KILL -f "$PROCESS"
}

case "${1:-}" in
    ""|start)
        start_shell
        ;;
    stop)
        stop_shell || echo "zenith-shell is not running"
        ;;
    restart)
        stop_shell
        start_shell
        ;;
    status)
        if pids=$(pgrep -f "$PROCESS"); then
            echo "zenith-shell is running (pid ${pids//$'\n'/, })"
        else
            echo "zenith-shell is not running"
            exit 1
        fi
        ;;
    -h|--help|help)
        cat <<'EOF'
Usage:
    zenith-shell [start]          start the shell
    zenith-shell stop             stop the shell
    zenith-shell restart          restart the shell
    zenith-shell status           show whether the shell is running
    zenith-shell lock [-f]        lock the screen (-f: return once locked)
    zenith-shell settings         open the settings window
    zenith-shell setup <cmd>      install | sync | update | doctor | uninstall | logs
                                  (zenith-shell setup --help for details)
    zenith-shell -V, --version    show the installed version
    zenith-shell -h, --help       show this message
EOF
        ;;
    -V|--version)
        echo "zenith-shell $(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
        ;;
    lock)
        # foreground + exec: xss-lock and swayidle -w watch this process,
        # and xss-lock's sleep fd must reach the locker
        shift
        exec "@VENV@/bin/python" -m lock "$@"
        ;;
    settings)
        exec "@VENV@/bin/python" -m settings
        ;;
    setup)
        shift
        export ZENITH_PROG="zenith-shell setup"
        export ZENITH_DIR="@INSTALL_DIR@"
        py="@VENV@/bin/python"
        "$py" -c '' 2>/dev/null || py=python3
        exec "$py" installer/main.py "$@"
        ;;
    *)
        echo "zenith-shell: unknown command '$1'" >&2
        match=$(python3 -c 'import difflib, sys; print(*difflib.get_close_matches(sys.argv[1], sys.argv[2:], 1))' "$1" "${COMMANDS[@]}" 2>/dev/null)
        [[ -z "$match" ]] || echo "Did you mean: zenith-shell $match" >&2
        echo "See: zenith-shell --help" >&2
        exit 2
        ;;
esac
"""


def step_launchers() -> None:
    c.BIN_DIR.mkdir(parents=True, exist_ok=True)
    launcher = c.BIN_DIR / c.SHELL_NAME
    launcher.write_text(
        LAUNCHER.replace("@INSTALL_DIR@", str(c.INSTALL_DIR))
        .replace("@VENV@", str(c.VENV_DIR))
        .replace("@PROCESS@", c.SHELL_PROCESS)
    )
    launcher.chmod(0o755)
    (c.BIN_DIR / f"{c.SHELL_NAME}-setup").unlink(
        missing_ok=True
    )  # installs before the merge had a 2nd launcher
    ok(f"Launcher: {launcher.name}  (try: zenith-shell --help)")


def step_completions() -> None:
    source_dir = Path(__file__).resolve().parent / "completions"
    installed = []
    for shell, (source, target) in COMPLETIONS.items():
        if not c.have(shell):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_dir / source, target)
        installed.append(shell)
    ok(f"Tab completion: {', '.join(installed) or 'no supported shell found'}")


def step_bootstrap(wms: list[str]) -> None:
    """Write the config for each WM, whichever session the installer is running in."""
    for wm in wms:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(c.INSTALL_DIR)
        env["ZENITH_BOOTSTRAP_WM"] = wm
        run(
            [c.VENV_DIR / "bin" / "python", "-m", "config.bootstrap"],
            cwd=c.INSTALL_DIR,
            env=env,
            label=f"Writing {wm} config",
        )


# ----------------------------------------------------------------------------
# Pre-flight stage
# ----------------------------------------------------------------------------
def report_problems(problems) -> None:
    lines = []
    for problem in problems:
        lines.append(f"{RED}{SYM['err']}{NC} {problem.msg}")
        lines += [f"    {DIM}{hint}{NC}" for hint in problem.hint.splitlines()]
    plural = "" if len(problems) == 1 else "s"
    panel(
        f"{len(problems)} problem{plural} found – stopped before installing anything",
        lines,
        RED,
    )


def preflight_stage(backend, plan, command):
    c.step("Pre-flight checks")
    if plan.needs_work and not c.OPTS.dry_run:
        c.ensure_sudo()
        backend.prepare()
    problems = backend.preflight(plan, command)

    fixable = [p for p in problems if p.fix]
    if fixable and not c.OPTS.dry_run:
        lines = [f"{SYM['dot']} {p.msg}" for p in fixable] + [""]
        lines += [f"{SYM['dot']} will {p.fix_desc}" for p in fixable]
        panel("Missing prerequisites I can install for you", lines, YELLOW)
        if c.confirm("Install them now?"):
            for problem in fixable:
                problem.fix()
            plan = backend.plan(plan.wms)
            problems = backend.preflight(plan, command)

    if c.OPTS.dry_run:
        for problem in fixable:
            info(f"Would offer to {problem.fix_desc}.")
        problems = [p for p in problems if not p.fix]

    if problems:
        report_problems(problems)
        raise SystemExit(1)
    ok("All checks passed – nothing should surprise you later.")
    return plan


def show_plan(plan, backend, configure: list[str]) -> None:
    present = len(plan.pkgs) - len(plan.missing_pkgs)
    lines = [
        f"Distro     : {backend.pretty}",
        f"WM(s)      : {', '.join(plan.wms)}",
        f"Packages   : {len(plan.missing_pkgs)} to install ({present} already present)",
    ]
    if plan.missing_pkgs:
        lines.append(
            f"{DIM}{' ' * 13}{' '.join(plan.missing_pkgs)}{NC}"
        )  # long lists are wrapped by panel()
    if plan.tools:
        lines.append(f"Build      : {', '.join(t.name for t in plan.tools)}")
    if configure:
        lines.append(f"Configure  : {', '.join(configure)}")
    lines += backend.plan_notes(plan)
    panel("Plan", lines)


# ----------------------------------------------------------------------------
# doctor
# ----------------------------------------------------------------------------
CONFLICT_FIX = (
    "rebind the key in zenith-shell settings (Keybindings tab) or remove it from "
    "your window manager config, then reload the window manager"
)


def keybinding_conflicts(wms: list[str]) -> dict:
    found = {wm: find_wm_conflicts(wm) for wm in wms}
    return {wm: conflicts for wm, conflicts in found.items() if conflicts}


def conflict_lines(conflicts) -> list[str]:
    return [
        f"{conflict.key}: {' / '.join(conflict.commands)}" for conflict in conflicts
    ]


def cmd_doctor(args, backend) -> int:
    wms = c.resolve_wms(args.wm)
    if not wms:
        raise InstallError("Could not detect i3 or sway. Re-run with --wm i3|sway|all.")
    plan = backend.plan(wms)

    lines = []
    for feature in plan.features:
        pkgs = backend.PACKAGES.get(feature, [])
        missing = [p for p in pkgs if p in plan.missing_pkgs]
        lines.append(
            f"{mark(not missing)} {feature:<8} {len(pkgs) - len(missing)}/{len(pkgs)} packages"
        )
        if missing:
            lines.append(f"    {DIM}missing: {' '.join(missing)}{NC}")
    for tool in backend.TOOLS:
        if tool.feature in plan.features:
            lines.append(f"{mark(tool not in plan.tools)} tool: {tool.name}")

    launcher = c.BIN_DIR / c.SHELL_NAME
    on_path = str(c.BIN_DIR) in c.ORIGINAL_PATH.split(":")
    unconfigured = [
        wm for wm in wms if c.have(wm) and not c.wm_autostart_configured(wm)
    ]
    not_installed = [wm for wm in wms if not c.have(wm)]
    conflicts = keybinding_conflicts(wms)
    setup_checks = {
        "virtualenv": c.venv_ok(),
        "launcher": os.access(launcher, os.X_OK),
        "fonts": all((FONT_DIR / name).exists() for name in FONTS),
    }
    for name, good in setup_checks.items():
        lines.append(f"{mark(good)} {name}")
    lines.append(f"{mark(on_path)} {c.BIN_DIR} in PATH")
    for wm in wms:
        if wm in not_installed:
            lines.append(f"{mark(False)} {wm} is not installed")
        else:
            lines.append(f"{mark(wm not in unconfigured)} {wm} autostart")
            lines.append(f"{mark(wm not in conflicts)} {wm} keybindings")
            lines += [
                f"    {DIM}{line}{NC}" for line in conflict_lines(conflicts.get(wm, []))
            ]

    target = "all" if len(wms) > 1 else wms[0]
    fixes = []
    if not all(setup_checks.values()):
        fixes.append(f"{c.INSTALL_DIR}/installer/install.sh --wm {target}")
    elif plan.needs_work or unconfigured:
        fixes.append(f"zenith-shell setup sync --wm {target}")
    if not_installed:
        fixes.append(
            f"install {' and '.join(not_installed)}, then: zenith-shell setup sync --wm {target}"
        )
    if conflicts:
        fixes.append(CONFLICT_FIX)
    if not on_path:
        fixes.append('add to your shell rc: export PATH="$HOME/.local/bin:$PATH"')

    panel(f"Doctor – {'+'.join(wms)}", lines, YELLOW if fixes else GREEN)
    for fix in fixes:
        info(f"Fix with:  {fix}")
    return 1 if fixes else 0


# ----------------------------------------------------------------------------
# install / sync
# ----------------------------------------------------------------------------
def report_keybinding_conflicts(wms: list[str]) -> int:
    """Nothing is edited: the user decides which binding keeps the key. Returns the exit code."""
    conflicts = keybinding_conflicts(wms)
    for wm, found in conflicts.items():
        panel(
            f"{wm} has conflicting keybindings",
            [
                *conflict_lines(found),
                "",
                "Zenith's launcher or other shortcuts may not work until this is fixed.",
            ],
            RED,
        )
    if conflicts:
        info(f"Fix with:  {CONFLICT_FIX}")
    return 1 if conflicts else 0


def notices(plan) -> None:
    if "x11" in plan.features:
        lines = [
            f"Config shipped in: {c.INSTALL_DIR}/config/picom",
            (
                "Needs upstream picom v12+; older or distro-patched builds using legacy syntax "
                "may warn or lose effects: https://github.com/yshui/picom"
            ),
            "",
            (
                "Do NOT enable screen corners without picom running: the corner window spans the "
                "whole screen and is not transparent, so everything turns black."
            ),
        ]
        if not c.have("picom"):
            lines += [
                "",
                "Picom is not installed – compositor effects are disabled by default.",
            ]
        panel("Picom (compositor)", lines, YELLOW)
    if str(c.BIN_DIR) not in c.ORIGINAL_PATH.split(":"):
        panel(
            "Action required",
            [
                f"{c.BIN_DIR} is not in your PATH. Add to ~/.bashrc / ~/.zshrc:",
                "",
                '  export PATH="$HOME/.local/bin:$PATH"',
            ],
            YELLOW,
        )
    if os.environ.get("SHELL", "").endswith("zsh") and str(
        ZSH_COMPLETION_DIR
    ) not in os.environ.get("FPATH", ""):
        panel(
            "Tab completion in zsh",
            [
                "Add this to ~/.zshrc, before compinit runs:",
                "",
                f"  fpath=({ZSH_COMPLETION_DIR} $fpath)",
            ],
            YELLOW,
        )


def cmd_install_or_sync(args, backend, command: str) -> int:
    """install, sync and the second half of update share one flow: plan -> pre-flight -> steps."""
    started = time.time()
    if command in ("sync", "update") and not c.INSTALL_DIR.exists():
        raise InstallError(
            "Zenith Shell is not installed yet – run `install.sh` first."
        )

    wms = c.resolve_wms(args.wm)
    if not wms:
        raise InstallError("Could not detect i3 or sway. Re-run with --wm i3|sway|all.")

    if command == "install":
        print(f"{BLUE}{LOGO}{NC}", end="")
    suffix = " (dry run)" if args.dry_run else ""
    panel(
        f"Zenith Shell – {command}{suffix}",
        [
            f"Distro  : {backend.pretty}",
            f"WM(s)   : {', '.join(wms)}",
            f"Log     : {c.LOG_FILE}",
        ],
    )

    plan = backend.plan(wms)
    # sync only touches WM configs that lack our lines; install and update refresh them all
    targets = (
        [wm for wm in wms if not c.wm_autostart_configured(wm)]
        if command == "sync"
        else wms
    )
    # Without the WM there is no system config to start from, and a config holding only
    # our lines would later hide its defaults ($mod, font, basic keybindings).
    configure = [wm for wm in targets if c.have(wm)]
    not_installed = [wm for wm in targets if not c.have(wm)]
    steps = []
    if plan.missing_pkgs:
        steps.append(
            ("Installing system packages", lambda p: backend.install_packages(p))
        )
    if plan.tools:
        steps.append(("Building tools from source", lambda p: backend.install_tools(p)))
    if command in ("install", "update"):
        steps += [
            (
                "Python environment",
                lambda p: step_python_env(backend, upgrade_pip=command == "install"),
            ),
            ("Fonts", lambda p: step_fonts()),
            ("Launcher", lambda p: step_launchers()),
            ("Tab completion", lambda p: step_completions()),
        ]
    elif configure and not c.venv_ok():  # bootstrap runs inside the virtualenv
        steps.append(("Python environment", lambda p: step_python_env(backend)))
    if configure:
        steps.append(("Window manager config", lambda p: step_bootstrap(configure)))

    c.set_total(len(steps) + 1)
    plan = preflight_stage(backend, plan, command)
    show_plan(plan, backend, configure)
    for wm in not_installed:
        warn(
            f"{wm} is not installed, so its config was skipped. Install it, then run: zenith-shell setup sync --wm {wm}"
        )

    if command == "sync" and not plan.needs_work and not configure:
        c.save_state(wms, backend.name)
        ok(f"Everything for {'+'.join(wms)} is already installed.")
        return report_keybinding_conflicts(wms)
    if args.dry_run:
        info("Dry run – nothing was changed.")
        return 0
    if command == "install" and c.shell_running():
        warn(
            "Zenith Shell is running. A full install replaces its code and Python packages – "
            "restart it afterwards: zenith-shell restart"
        )
    if command != "update" and not c.confirm(
        "Continue?"
    ):  # update already asked before pulling
        info("Aborted.")
        return 1

    for title, fn in steps:
        c.step(title)
        fn(plan)

    c.save_state(
        wms,
        backend.name,
        packages=plan.missing_pkgs,
        tools=[t.name for t in plan.tools],
    )
    print()
    ok(f"Done in {c.fmt_time(time.time() - started)}")
    if command == "update":
        state = c.load_state()
        ok(f"Updated {state.get('update_from', '?')} -> {state.get('update_to', '?')}")
        c.update_state(pending_update=None)
    if command == "install":
        print(f"{BLUE}{LOGO}{NC}")
        print(f"To start, run: {BOLD}zenith-shell{NC}, or restart your session.")
    if c.shell_running():
        info(
            f"Zenith Shell is still running the old components – apply the changes with: {BOLD}zenith-shell restart{NC}"
        )
    if command != "update":
        notices(plan)
        info(f"Switched window manager later? Run: {BOLD}zenith-shell setup sync{NC}")
    return report_keybinding_conflicts(wms)


# ----------------------------------------------------------------------------
# update
# ----------------------------------------------------------------------------
def git_out(*args: str, strip: bool = True) -> str:
    rc, out = c.capture(["git", "-C", str(c.INSTALL_DIR), *args])
    if rc != 0:
        return ""
    return out.strip() if strip else out.rstrip("\n")


def cmd_update(args, backend) -> int:
    """Phase 1 (this code = the OLD version): fetch + fast-forward pull.
    Phase 2 (`--after-pull`): re-exec so the freshly pulled installer with its possibly changed
    package lists. Does the dependency sync, pip, launcher and bootstrap steps.
    """
    if not (c.INSTALL_DIR / ".git").is_dir():
        raise InstallError(
            f"{c.INSTALL_DIR} is not a git checkout – nothing to update. Run install.sh instead."
        )
    if args.after_pull:
        return cmd_install_or_sync(args, backend, "update")

    dot = SYM["dot"]
    upstream = git_out("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        raise InstallError(
            "The checkout has no upstream branch (detached HEAD?). "
            f"Fix with: git -C {c.INSTALL_DIR} checkout main"
        )
    suffix = " (dry run)" if args.dry_run else ""
    panel(
        f"Zenith Shell – update{suffix}",
        [
            f"Checkout : {c.INSTALL_DIR}",
            f"Tracking : {upstream}",
            f"Log      : {c.LOG_FILE}",
        ],
    )

    git = ["git", "-C", str(c.INSTALL_DIR)]
    run([*git, "fetch", "--quiet"], label="Fetching latest changes")
    old = git_out("rev-parse", "--short", "HEAD")
    incoming = int(git_out("rev-list", "--count", "HEAD..@{u}") or 0)
    local_ahead = int(git_out("rev-list", "--count", "@{u}..HEAD") or 0)

    if incoming == 0:
        if c.load_state().get("pending_update"):
            warn("A previous update did not finish – resuming it.")
            return cmd_install_or_sync(args, backend, "update")
        ok(f"Already up to date ({old}).")
        if local_ahead:
            info(f"You have {local_ahead} local commit(s) that are not on {upstream}.")
        return 0
    if local_ahead:
        raise InstallError(
            f"Your checkout has {local_ahead} local commit(s) not on {upstream}, so it cannot "
            f"fast-forward. Rebase it yourself: git -C {c.INSTALL_DIR} pull --rebase"
        )

    shown = git_out(
        "log", "--oneline", "--no-decorate", "-n", "12", "HEAD..@{u}"
    ).splitlines()
    lines = [f"{dot} {line}" for line in shown]
    if incoming > len(shown):
        lines.append(f"{DIM}... and {incoming - len(shown)} more{NC}")
    panel(f"{incoming} new commit{'s' if incoming != 1 else ''}", lines)

    # Local edits are fine as long as the update doesn't touch the same files.
    # If it does, stop BEFORE pulling -> no stashes, no conflict markers in your config.
    dirty = [
        line[3:].strip()
        for line in git_out(
            "status", "--porcelain", "--untracked-files=no", strip=False
        ).splitlines()
    ]
    clash = sorted(
        set(dirty) & set(git_out("diff", "--name-only", "HEAD..@{u}").splitlines())
    )
    if clash:
        panel(
            "Local edits clash with this update",
            [f"{dot} {name}" for name in clash]
            + [
                "",
                "These files are changed upstream too. Save your version elsewhere or stash it, then run the update again:",
                f"  git -C {c.INSTALL_DIR} stash        (re-apply later with: git stash pop)",
            ],
            RED,
        )
        return 1
    if dirty:
        panel(
            "Local changes (left untouched)",
            [f"{dot} {name}" for name in dirty[:10]],
            YELLOW,
        )
    if args.dry_run:
        info("Dry run – nothing was pulled. (Only `git fetch` ran.)")
        return 0
    if c.shell_running():
        info(
            "Zenith Shell is running; restart it after the update: zenith-shell restart"
        )
    if not c.confirm("Update now?"):
        info("Aborted.")
        return 1

    run([*git, "pull", "--ff-only"], label="Pulling changes")
    new = git_out("rev-parse", "--short", "HEAD")
    c.update_state(
        pending_update=True, update_from=old, update_to=new
    )  # cleared once phase 2 succeeds
    ok(f"Repository updated {old} -> {new}")
    info("Continuing with the new version of the installer...")
    sys.stdout.flush()
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(c.INSTALL_DIR / "installer" / "main.py"),
            "update",
            "--after-pull",
            "--wm",
            args.wm,
            *(["--yes"] if args.yes else []),
            *(["--verbose"] if args.verbose else []),
        ],
    )


# ----------------------------------------------------------------------------
# uninstall
# ----------------------------------------------------------------------------
def scan_wm_configs() -> list[Path]:
    """Files in the WM configs that mention zenith or link into the install dir.
    These belong to the user: we list them for manual cleanup and never delete them."""
    found: list[Path] = []
    install = Path(os.path.realpath(c.INSTALL_DIR))
    for wm in c.WM_FEATURE:
        for dirpath, dirnames, filenames in os.walk(c.HOME / ".config" / wm):
            for name in [*dirnames, *filenames]:
                path = Path(dirpath) / name
                if path.is_symlink():
                    if Path(os.path.realpath(path)).is_relative_to(install):
                        found.append(path)
                    continue
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_size < 1_000_000 and (
                        "zenith" in name.lower()
                        or "zenith" in path.read_text(errors="ignore").lower()
                    ):
                        found.append(path)
                except OSError:
                    pass
    return found


def has_local_work() -> bool:
    """Would deleting the install dir lose commits or edits that exist nowhere else?"""
    if c.INSTALL_DIR.is_symlink() or not (c.INSTALL_DIR / ".git").is_dir():
        return False
    edited = git_out("status", "--porcelain", "--untracked-files=no")
    unpushed = git_out("rev-list", "--count", "@{u}..HEAD")
    return bool(edited) or unpushed not in ("", "0")


def remove_tree(path: Path) -> None:
    if path.is_symlink():  # remove the link, never what it points to
        path.unlink()
        return
    if not path.exists():
        return
    resolved, home = path.resolve(), c.HOME.resolve()
    if resolved == home or resolved in home.parents:
        raise InstallError(
            f"Refusing to remove {path}: it is your home directory or above."
        )
    is_install_dir = (
        resolved == c.INSTALL_DIR.resolve()
        and (resolved / "installer" / "main.py").is_file()
    )
    if not (is_install_dir or path.name == c.SHELL_NAME):
        raise InstallError(f"Refusing to remove {path}: not a Zenith Shell directory.")
    try:
        shutil.rmtree(path)
    except PermissionError:  # e.g. files left root-owned by `sudo ninja install`
        c.ensure_sudo()
        run(
            ["rm", "-rf", "--one-file-system", "--", resolved],
            sudo=True,
            label=f"Removing {path} (root-owned files)",
        )


def cmd_uninstall(args, backend) -> int:
    state = c.load_state()
    config = c.CONFIG_DIR / "config.json"
    launchers = [
        p
        for p in (c.BIN_DIR / c.SHELL_NAME, c.BIN_DIR / f"{c.SHELL_NAME}-setup")
        if p.exists() or p.is_symlink()
    ]
    completions = [target for _, target in COMPLETIONS.values() if target.exists()]
    if not (c.INSTALL_DIR.exists() or launchers or FONT_DIR.exists() or state):
        info("Nothing to uninstall.")
        return 0

    built = list(state.get("tools", []))
    mentions = scan_wm_configs()
    local_work = has_local_work()
    if local_work and c.OPTS.yes:
        raise InstallError(
            f"{c.INSTALL_DIR} has local edits or unpushed commits. "
            "Re-run without --yes to confirm deleting them."
        )
    dot = SYM["dot"]

    lines = [f"{dot} stop running Zenith Shell processes"]
    if c.INSTALL_DIR.is_symlink():
        lines.append(f"{dot} delete the {c.INSTALL_DIR} symlink (its target is kept)")
    else:
        lines.append(
            f"{dot} delete {c.INSTALL_DIR} (code, virtualenv, vendored sources)"
        )
    if local_work:
        lines.append(f"{RED}{SYM['warn']} it has local edits or unpushed commits!{NC}")
    if launchers:
        lines.append(f"{dot} delete launchers: {', '.join(p.name for p in launchers)}")
    if completions:
        lines.append(f"{dot} delete tab completion files")
    lines += [
        f"{dot} delete fonts in {FONT_DIR}",
        f"{dot} delete installer state and logs",
    ]
    if built and args.purge:
        lines.append(f"{dot} remove tools built from source: {', '.join(built)}")
    elif built:
        lines.append(
            f"{DIM}Tools built from source are kept ({', '.join(built)}); "
            f"other Fabric-based shells may use them. To remove them, use --purge now: "
            f"they can't be tracked after this uninstall.{NC}"
        )
    lines.append(f"{DIM}System packages are never removed automatically.{NC}")
    panel("Uninstall plan", lines, YELLOW)

    if args.dry_run:
        info("Dry run – nothing was changed.")
        return 0

    keep_config = not c.CONFIG_DIR.exists() or c.confirm(
        f"Keep your settings ({c.CONFIG_DIR})?", default=True
    )
    if not c.confirm("Uninstall Zenith Shell now?", default=False):
        info("Aborted.")
        return 1

    def stop_processes() -> None:
        ok("Stopped running instances" if c.stop_shell() else "Nothing was running")

    def remove_built_tools() -> None:
        if any(name != "matugen" for name in built):
            c.ensure_sudo()
        backend.uninstall_tools(built)

    def remove_launchers() -> None:
        for path in [*launchers, *completions]:
            path.unlink(missing_ok=True)
        ok("Removed launchers and tab completion")

    def remove_fonts() -> None:
        remove_tree(FONT_DIR)
        if c.have("fc-cache"):
            run(["fc-cache", "-f"], check=False, label="Updating font cache")

    steps = [("Stopping Zenith Shell", stop_processes)]
    if args.purge and built:
        steps.append(
            ("Removing source-built tools", remove_built_tools)
        )  # needs vendors/, so before the next steps
    steps += [
        ("Removing launchers", remove_launchers),
        ("Removing fonts", remove_fonts),
        ("Removing Zenith Shell", lambda: remove_tree(c.INSTALL_DIR)),
    ]
    if not keep_config:
        steps.append(("Removing your settings", lambda: remove_tree(c.CONFIG_DIR)))
    steps += [
        (
            "Cleaning up",
            lambda: [remove_tree(c.STATE_FILE.parent), remove_tree(c.LOG_FILE.parent)],
        ),
    ]

    c.set_total(len(steps))
    for title, fn in steps:
        c.step(title)
        fn()

    print()
    ok("Zenith Shell has been removed.")
    if keep_config and config.exists():
        info(f"Your settings are kept in {config}.")
    if mentions:
        panel(
            "Leftover references – edit these by hand",
            [str(p) for p in mentions]
            + [
                "",
                "Remove the lines that mention zenith (include / exec / bindsym),",
                "and any symlinks into the old install directory.",
            ],
            YELLOW,
        )
    pkgs = state.get("packages", [])
    if pkgs and backend.REMOVE_CMD:
        panel(
            "Packages the installer added (kept)",
            [
                f"{DIM}Other software may depend on these – review before removing:{NC}",
                "",
                f"{backend.REMOVE_CMD} {' '.join(pkgs)}",
            ],
            BLUE,
        )
    return 0


# ----------------------------------------------------------------------------
# logs
# ----------------------------------------------------------------------------
def cmd_logs(args) -> int:
    if not c.LOG_FILE.exists():
        info(f"No installer log yet ({c.LOG_FILE}).")
        return 0
    with open(c.LOG_FILE, encoding="utf-8", errors="replace") as log:
        sys.stdout.writelines(collections.deque(log, maxlen=max(args.lines, 0)))
    info(f"Full log: {c.LOG_FILE}")
    return 0


# ----------------------------------------------------------------------------
# command line
# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=os.environ.get("ZENITH_PROG", "main.py"),
        description="Zenith Shell installer",
    )
    commands = parser.add_subparsers(
        dest="command", metavar="<command>", title="commands"
    )

    wm = argparse.ArgumentParser(add_help=False)
    wm.add_argument(
        "--wm",
        default="auto",
        choices=["auto", "i3", "sway", "all"],
        help="window manager(s) to set up (default: auto, detected)",
    )
    changes = argparse.ArgumentParser(add_help=False)
    changes.add_argument(
        "--dry-run",
        action="store_true",
        help="run the checks and show the plan without changing anything",
    )
    changes.add_argument(
        "-y", "--yes", action="store_true", help="never ask for confirmation"
    )
    changes.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show command output as it runs",
    )

    def add(name, help_text, parents):
        return commands.add_parser(
            name, help=help_text, description=help_text, parents=parents
        )

    add(
        "install",
        "Full install: dependencies, virtualenv, fonts and WM config",
        [wm, changes],
    )
    add(
        "sync",
        "Install what is missing and configure the selected WM(s)",
        [wm, changes],
    )
    update = add(
        "update",
        "Pull the latest version, then sync dependencies and re-apply setup",
        [wm, changes],
    )
    update.add_argument("--after-pull", action="store_true", help=argparse.SUPPRESS)
    add("doctor", "Check dependencies and setup", [wm])
    uninstall = add(
        "uninstall",
        "Remove Zenith Shell (asks whether to keep your settings)",
        [changes],
    )
    uninstall.add_argument(
        "--purge",
        action="store_true",
        help="also remove tools built from source from the system",
    )
    logs = add("logs", "Show the end of the installer log", [])
    logs.add_argument(
        "-n", "--lines", type=int, default=50, help="lines to show (default: 50)"
    )
    return parser


def normalize_argv(argv: list[str], parser: argparse.ArgumentParser) -> list[str]:
    """Allow the command anywhere (`--wm i3 sync`) and suggest a fix for a mistyped one."""
    argv = list(argv)
    if "--distro" in argv:
        # Older versions pass this when they hand over to this code during `update`.
        at = argv.index("--distro")
        del argv[at : at + 2]
    names = list(
        next(
            action.choices
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
    )
    for at, word in enumerate(argv):
        if word in names:
            return [word, *argv[:at], *argv[at + 1 :]]
    if argv and not argv[0].startswith("-"):
        match = difflib.get_close_matches(argv[0], names, 1)
        hint = f" (did you mean '{match[0]}'?)" if match else ""
        parser.error(f"unknown command '{argv[0]}'{hint}")
    return argv


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:], parser))

    if args.command is None:  # bare `zenith-shell setup`
        names = ["sync", "update", "doctor", "install", "uninstall", "logs"]
        picked = c.choose("What do you want to do?", names)
        if picked is None:
            parser.print_help()
            return 0
        args = parser.parse_args([picked])

    c.OPTS.yes = getattr(args, "yes", False)
    c.OPTS.dry_run = getattr(args, "dry_run", False)
    c.OPTS.verbose = getattr(args, "verbose", False)

    try:
        if args.command == "logs":
            return cmd_logs(args)
        backend = load_backend(c.detect_distro())
        if args.command == "doctor":
            return cmd_doctor(args, backend)
        if args.command == "uninstall":
            return cmd_uninstall(args, backend)
        if args.command == "update":
            return cmd_update(args, backend)
        return cmd_install_or_sync(args, backend, args.command)
    except (InstallError, OSError) as exc:
        panel(
            f"{args.command} failed",
            [
                str(exc),
                "",
                "Completed work is detected automatically,",
                "so after fixing the cause just run the same command again.",
            ],
            RED,
        )
        return 1
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{NC}")
        return 130


if __name__ == "__main__":
    sys.exit(main())
