import os
import time

from installer.commands.steps import (
    step_bootstrap,
    step_completions,
    step_fonts,
    step_launchers,
    step_python_env,
)
from installer.paths import BIN_DIR, INSTALL_DIR, LOG_FILE, ORIGINAL_PATH, ZSH_COMPLETION_DIR
from installer.state import load_state, save_state, update_state
from installer.system import InstallError, ensure_sudo, have, shell_running, venv_ok
from installer.ui import (
    BLUE,
    BOLD,
    DIM,
    NC,
    OPTS,
    RED,
    SYM,
    YELLOW,
    confirm,
    fmt_time,
    info,
    ok,
    panel,
    set_total,
    step,
    warn,
)
from installer.wm import report_keybinding_conflicts, resolve_wms, wm_autostart_configured


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


def report_problems(problems) -> None:
    lines = []
    for problem in problems:
        lines.append(f"{RED}{SYM['err']}{NC} {problem.msg}")
        lines += [f"    {DIM}{hint}{NC}" for hint in problem.hint.splitlines()]
    plural = "" if len(problems) == 1 else "s"
    panel(
        f"{len(problems)} problem{plural} found. Nothing was installed",
        lines,
        RED,
    )


def preflight_stage(backend, plan, command):
    step("Pre-flight checks")
    if plan.needs_work and not OPTS.dry_run:
        ensure_sudo()
        backend.prepare()
    problems = backend.preflight(plan, command)

    fixable = [p for p in problems if p.fix]
    if fixable and not OPTS.dry_run:
        lines = [f"{SYM['dot']} {p.msg}" for p in fixable] + [""]
        lines += [f"{SYM['dot']} will {p.fix_desc}" for p in fixable]
        panel("Missing prerequisites", lines, YELLOW)
        if confirm("Install them now?"):
            for problem in fixable:
                problem.fix()
            plan = backend.plan(plan.wms)
            problems = backend.preflight(plan, command)

    if OPTS.dry_run:
        for problem in fixable:
            info(f"Would offer to {problem.fix_desc}.")
        problems = [p for p in problems if not p.fix]

    if problems:
        report_problems(problems)
        raise SystemExit(1)
    ok("All checks passed.")
    return plan


def show_plan(plan, backend, configure: list[str]) -> None:
    present = len(plan.pkgs) - len(plan.missing_pkgs)
    lines = [
        f"Distro     : {backend.pretty}",
        f"WM(s)      : {', '.join(plan.wms)}",
        f"Packages   : {len(plan.missing_pkgs)} to install ({present} already present)",
    ]
    if plan.missing_pkgs:
        # panel() wraps long lists
        lines.append(f"{DIM}{' ' * 13}{' '.join(plan.missing_pkgs)}{NC}")
    if plan.tools:
        lines.append(f"Build      : {', '.join(t.name for t in plan.tools)}")
    if configure:
        lines.append(f"Configure  : {', '.join(configure)}")
    lines += backend.plan_notes(plan)
    panel("Plan", lines)


def notices(plan) -> None:
    if "x11" in plan.features:
        lines = [
            f"Config shipped in: {INSTALL_DIR}/config/picom",
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
        if not have("picom"):
            lines += [
                "",
                "Picom is not installed, so compositor effects are disabled by default.",
            ]
        panel("Picom (compositor)", lines, YELLOW)
    if str(BIN_DIR) not in ORIGINAL_PATH.split(":"):
        panel(
            "Action required",
            [
                f"{BIN_DIR} is not in your PATH. Add to ~/.bashrc / ~/.zshrc:",
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
    if command in ("sync", "update") and not INSTALL_DIR.exists():
        raise InstallError(
            "Zenith Shell is not installed yet. Run `install.sh` first."
        )

    wms = resolve_wms(args.wm)
    if not wms:
        raise InstallError(
            "Could not detect i3, sway or Hyprland. "
            "Re-run with --wm i3|sway|hyprland|all."
        )

    if command == "install":
        print(f"{BLUE}{LOGO}{NC}", end="")
    suffix = " (dry run)" if args.dry_run else ""
    panel(
        f"Zenith Shell: {command}{suffix}",
        [
            f"Distro  : {backend.pretty}",
            f"WM(s)   : {', '.join(wms)}",
            f"Log     : {LOG_FILE}",
        ],
    )

    plan = backend.plan(wms)
    # sync only touches WM configs that lack our lines; install and update refresh them all
    targets = (
        [wm for wm in wms if not wm_autostart_configured(wm)]
        if command == "sync"
        else wms
    )
    # Without the WM there is no system config to start from, and a config holding only
    # our lines would later hide its defaults ($mod, font, basic keybindings).
    configure = [wm for wm in targets if have(wm)]
    not_installed = [wm for wm in targets if not have(wm)]
    steps = []
    # steps get the plan pre-flight settles on, not this one
    if plan.missing_pkgs:
        steps.append(("Installing system packages", backend.install_packages))
    if plan.tools:
        steps.append(("Building tools from source", backend.install_tools))
    if command in ("install", "update"):
        steps += [
            (
                "Python environment",
                lambda _: step_python_env(backend, upgrade_pip=command == "install"),
            ),
            ("Fonts", lambda _: step_fonts()),
            ("Launcher", lambda _: step_launchers()),
            ("Tab completion", lambda _: step_completions()),
        ]
    elif configure and not venv_ok():  # bootstrap runs inside the virtualenv
        steps.append(("Python environment", lambda _: step_python_env(backend)))
    if configure:
        steps.append(("Window manager config", lambda _: step_bootstrap(configure)))

    set_total(len(steps) + 1)
    plan = preflight_stage(backend, plan, command)
    show_plan(plan, backend, configure)
    for wm in not_installed:
        warn(
            f"{wm} is not installed, so its config was skipped. Install it, then run: zenith-shell setup sync --wm {wm}"
        )

    if command == "sync" and not plan.needs_work and not configure:
        save_state(wms, backend.name)
        ok(f"Everything for {'+'.join(wms)} is already installed.")
        return report_keybinding_conflicts(wms)
    if args.dry_run:
        info("Dry run: nothing was changed.")
        return 0
    if command == "install" and shell_running():
        warn(
            "Zenith Shell is running. A full install replaces its code and Python packages, so "
            "restart it afterwards: zenith-shell restart"
        )
    # update already asked before pulling
    if command != "update" and not confirm("Continue?"):
        info("Aborted.")
        return 1

    for title, fn in steps:
        step(title)
        fn(plan)

    save_state(
        wms,
        backend.name,
        packages=plan.missing_pkgs,
        tools=[t.name for t in plan.tools],
    )
    print()
    ok(f"Done in {fmt_time(time.time() - started)}")
    if command == "update":
        state = load_state()
        ok(f"Updated {state.get('update_from', '?')} -> {state.get('update_to', '?')}")
        update_state(pending_update=None)
    if command == "install":
        print(f"To start, run: {BOLD}zenith-shell{NC}, or restart your session.")
    if shell_running():
        info(
            f"Zenith Shell is still running the old components. Apply the changes with: {BOLD}zenith-shell restart{NC}"
        )
    if command != "update":
        notices(plan)
        info(f"Switched window manager later? Run: {BOLD}zenith-shell setup sync{NC}")
    return report_keybinding_conflicts(wms)
