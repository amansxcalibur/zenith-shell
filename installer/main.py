"""Zenith Shell installer.

install     full install (default)
sync        install only what is missing for the selected WM(s)   <- use after switching i3 <-> sway
update      pull the latest git changes, then sync dependencies and re-apply setup
doctor      report present / missing dependencies
uninstall   remove Zenith Shell (optionally keeping your config.json)
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c
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
    if not c.VENV_DIR.exists():
        cmd = [sys.executable, "-m", "venv"]
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
    else:
        warn("requirements.txt not found, skipping Python deps.")


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
# zenith-shell                start the shell
# zenith-shell setup <cmd>    install | sync | update | doctor | uninstall   (zenith-shell setup --help)
# TODO: zenith-shell restart        stop the running shell and start it again
cd "@INSTALL_DIR@" || exit 1

case "${1:-}" in
    -h|--help|help)
        cat <<- 'EOF'
        Usage:
        zenith-shell                  start the shell
        zenith-shell setup <cmd>      install | sync | update | doctor | uninstall
                                        (zenith-shell setup --help for details)
        zenith-shell -h, --help       show this message
EOF
# no spaces before EOF please uWu
        exit 0
        ;;
    setup)
        shift
        export ZENITH_PROG="zenith-shell setup"
        py="@VENV@/bin/python"
        [[ -x "$py" ]] || py=python3
        case "${1:-}" in
            ""|-*) [[ "${1:-}" == -h || "${1:-}" == --help ]] || set -- --help ;;
        esac
        exec "$py" installer/main.py "$@"
        ;;
    # restart)
    #     shift
    #     pkill -f '^@TITLE@' || true
    #     for _ in $(seq 50); do               # wait up to 5s for a clean exit
    #         pgrep -f '^@TITLE@' >/dev/null || break
    #         sleep 0.1
    #     done
    #     if pgrep -f '^@TITLE@' >/dev/null; then
    #         pkill -9 -f '^@TITLE@' || true   # SIGTERM ignored: force it
    #         sleep 0.2
    #     fi
    #     ;;
esac

"@VENV@/bin/python" main.py "$@" &
disown
"""


def step_launchers() -> None:
    c.BIN_DIR.mkdir(parents=True, exist_ok=True)
    launcher = c.BIN_DIR / c.SHELL_NAME
    launcher.write_text(
        LAUNCHER.replace("@INSTALL_DIR@", str(c.INSTALL_DIR))
        .replace("@VENV@", str(c.VENV_DIR))
        .replace("@TITLE@", c.SHELL_TITLE)
    )
    launcher.chmod(0o755)
    (c.BIN_DIR / f"{c.SHELL_NAME}-setup").unlink(
        missing_ok=True
    )  # installs before the merge had a 2nd launcher
    ok(f"Launcher: {launcher.name}  (try: zenith-shell setup --help)")


def step_restore_config() -> None:
    """Fresh install after `uninstall` that kept the settings -> put them back."""
    backup = c.BACKUP_DIR / "config.json"
    target = c.INSTALL_DIR / "config" / "config.json"
    if backup.exists() and not c.STATE_FILE.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        ok(f"Restored your previous settings from {backup}")


def step_bootstrap(plan) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(c.INSTALL_DIR)
    env["ZENITH_WM"] = ",".join(
        plan.wms
    )  # e.g. "i3,sway" – lets config.bootstrap write the right snippets
    env["ZENITH_FEATURES"] = ",".join(plan.features)
    run(
        [c.VENV_DIR / "bin" / "python", "-m", "config.bootstrap"],
        cwd=c.INSTALL_DIR,
        env=env,
        label="Running Zenith bootstrap",
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

    if problems:
        report_problems(problems)
        raise SystemExit(1)
    ok("All checks passed – nothing should surprise you later.")
    return plan


def show_plan(plan, backend) -> None:
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
    panel("Plan", lines)


# ----------------------------------------------------------------------------
# doctor
# ----------------------------------------------------------------------------
def cmd_doctor(args, backend) -> int:
    quiet = args.quiet or args.notify
    if quiet:
        # Started from the shell: if this WM was already set up (or is unknown) nothing changed -> no work at all.
        current = c.current_wm()
        if current is None or current in c.load_state().get("wms", []):
            return 0
    wms = (
        [current] if quiet else c.resolve_wms(args.wm)
    )  # from the shell: only the WM we are running under
    if not wms:
        return 0
    plan = backend.plan(wms)
    healthy = not plan.needs_work
    if quiet:
        if not healthy:
            what = [*plan.missing_pkgs, *(t.name for t in plan.tools)]
            more = " ..." if len(what) > 4 else ""
            body = f"Missing for {'+'.join(wms)}: {', '.join(what[:4])}{more}. Run `zenith-shell setup sync`, then restart the shell."
            if args.notify:
                c.notify("Zenith Shell: some features are unavailable", body)
            else:
                print(f"zenith-shell: {body}", file=sys.stderr)
        return 0 if healthy else 1

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
    lines.append(f"{mark(c.VENV_DIR.exists())} virtualenv")
    panel(
        f"Doctor – {'+'.join(wms)}",
        lines,
        GREEN if healthy and c.VENV_DIR.exists() else YELLOW,
    )
    if not healthy:
        target = "both" if len(wms) > 1 else wms[0]
        info(f"Fix with:  zenith-shell setup sync --wm {target}")
    return 0 if healthy else 1


# ----------------------------------------------------------------------------
# install / sync
# ----------------------------------------------------------------------------
def notices(plan) -> None:
    for wm in plan.wms:
        panel(
            f"{wm} keybindings",
            [
                f"{c.SHELL_NAME} has added {wm} config snippets and keybindings.",
                "If you already have custom keybindings you may see duplicate-binding warnings.",
                f"Review: ~/.config/{wm}/config (or your included files)",
            ],
            YELLOW,
        )
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


def cmd_install_or_sync(args, backend, command: str) -> int:
    """install, sync and the second half of update share one flow: plan -> pre-flight -> steps."""
    started = time.time()
    if command in ("sync", "update") and not c.INSTALL_DIR.exists():
        raise InstallError(
            "Zenith Shell is not installed yet – run `install.sh` first."
        )

    wms = c.resolve_wms(args.wm)
    if not wms:
        raise InstallError(
            "Could not detect i3 or sway. Re-run with --wm i3|sway|both."
        )

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
        ]
        if command == "install":
            steps.append(("Your settings", lambda p: step_restore_config()))
        steps.append(("Zenith bootstrap", lambda p: step_bootstrap(p)))

    c.set_total(len(steps) + 1)
    plan = preflight_stage(backend, plan, command)
    show_plan(plan, backend)

    if command == "sync" and not plan.needs_work:
        c.save_state(wms, backend.name)
        ok(f"Everything for {'+'.join(wms)} is already installed.")
        return 0
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
    return 0


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
            "--distro",
            backend.name,
            "--wm",
            args.wm,
            *(["--yes"] if args.yes else []),
        ],
    )


# ----------------------------------------------------------------------------
# uninstall
# ----------------------------------------------------------------------------
def scan_wm_configs() -> tuple[list[Path], list[Path]]:
    """-> (symlinks pointing into the install dir, other files that mention 'zenith')"""
    links: list[Path] = []
    mentions: list[Path] = []
    install = os.path.realpath(c.INSTALL_DIR)
    for wm in c.WM_FEATURE:
        for dirpath, dirnames, filenames in os.walk(c.HOME / ".config" / wm):
            for name in [*dirnames, *filenames]:
                path = Path(dirpath) / name
                if path.is_symlink():
                    if os.path.realpath(path).startswith(install):
                        links.append(path)
                    continue
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_size < 1_000_000 and (
                        "zenith" in name.lower()
                        or "zenith" in path.read_text(errors="ignore").lower()
                    ):
                        mentions.append(path)
                except OSError:
                    pass
    return links, mentions


def remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
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


def backup_config(config: Path) -> Path:
    c.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = c.BACKUP_DIR / "config.json"
    if dest.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
        dest.rename(c.BACKUP_DIR / f"config.{stamp}.json")
    shutil.copy2(config, dest)
    return dest


def cmd_uninstall(args, backend) -> int:
    state = c.load_state()
    config = c.INSTALL_DIR / "config" / "config.json"
    launchers = [
        p
        for p in (c.BIN_DIR / c.SHELL_NAME, c.BIN_DIR / f"{c.SHELL_NAME}-setup")
        if p.exists() or p.is_symlink()
    ]
    if not (c.INSTALL_DIR.exists() or launchers or FONT_DIR.exists() or state):
        info("Nothing to uninstall.")
        return 0

    built = [name for name in state.get("tools", [])]
    links, mentions = scan_wm_configs()
    dot = SYM["dot"]

    lines = [
        f"{dot} stop running Zenith Shell processes",
        f"{dot} delete {c.INSTALL_DIR} (code, virtualenv, vendored sources)",
    ]
    if launchers:
        lines.append(f"{dot} delete launchers: {', '.join(p.name for p in launchers)}")
    if links:
        lines.append(
            f"{dot} delete {len(links)} WM config symlink(s) pointing into the install dir"
        )
    lines += [
        f"{dot} delete fonts in {FONT_DIR}",
        f"{dot} delete installer state and logs",
    ]
    if built:
        lines.append(
            f"{dot} tools built from source ({', '.join(built)}): you will be asked"
        )
    lines.append(f"{DIM}System packages are never removed automatically.{NC}")
    panel("Uninstall plan", lines, YELLOW)

    if args.dry_run:
        info("Dry run – nothing was changed.")
        return 0

    keep_config = config.exists() and c.confirm(
        f"Keep your settings ({config})?", default=True
    )
    remove_tools = False
    if built:
        remove_tools = args.purge or (
            not c.OPTS.yes
            and c.confirm(
                f"Also remove the tools built from source ({', '.join(built)}) from the system? "
                "(other Fabric-based shells may use them)",
                default=False,
            )
        )
    if not c.confirm("Uninstall Zenith Shell now?", default=False):
        info("Aborted.")
        return 1

    saved: Path | None = None

    def stop_processes() -> None:
        ok("Stopped running instances" if c.stop_shell() else "Nothing was running")

    def remove_built_tools() -> None:
        if any(name != "matugen" for name in built):
            c.ensure_sudo()
        backend.uninstall_tools(built)

    def save_config() -> None:
        nonlocal saved
        saved = backup_config(config)
        ok(f"Settings saved to {saved}")

    def remove_launchers() -> None:
        for path in [*launchers, *links]:
            path.unlink(missing_ok=True)
        ok("Removed launchers and WM symlinks")

    def remove_fonts() -> None:
        remove_tree(FONT_DIR)
        if c.have("fc-cache"):
            run(["fc-cache", "-f"], check=False, label="Updating font cache")

    steps = [("Stopping Zenith Shell", stop_processes)]
    if remove_tools and built:
        steps.append(
            ("Removing source-built tools", remove_built_tools)
        )  # needs vendors/, so before the next steps
    if keep_config:
        steps.append(("Saving your settings", save_config))
    steps += [
        ("Removing launchers", remove_launchers),
        ("Removing fonts", remove_fonts),
        ("Removing Zenith Shell", lambda: remove_tree(c.INSTALL_DIR)),
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
    if saved:
        info(
            f"Your settings are in {saved} and come back automatically on the next fresh install."
        )
    if mentions:
        panel(
            "Leftover references – edit these by hand",
            [str(p) for p in mentions]
            + ["", "Remove the lines that mention zenith (include / exec / bindsym)."],
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog=os.environ.get("ZENITH_PROG", "install.sh"),
        description="Zenith Shell installer",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="install",
        choices=["install", "sync", "update", "doctor", "uninstall"],
    )
    parser.add_argument("--wm", default="auto", choices=["auto", "i3", "sway", "both"])
    parser.add_argument(
        "--distro", choices=["arch", "ubuntu"], default=os.environ.get("ZENITH_DISTRO")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="uninstall: also remove tools built from source",
    )
    parser.add_argument("-y", "--yes", action="store_true")
    parser.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--notify", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--after-pull", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.purge and args.command != "uninstall":
        parser.error("--purge only applies to the uninstall command")
    c.OPTS.yes, c.OPTS.dry_run = args.yes, args.dry_run

    try:
        backend = load_backend(args.distro or c.detect_distro())
        if args.command == "doctor":
            return cmd_doctor(args, backend)
        if args.command == "uninstall":
            return cmd_uninstall(args, backend)
        if args.command == "update":
            return cmd_update(args, backend)
        return cmd_install_or_sync(args, backend, args.command)
    except InstallError as exc:
        panel(
            "Installation failed",
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
    except subprocess.CalledProcessError as exc:
        c.err(f"Command failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
