#!/usr/bin/env python3
"""Zenith Shell installer.

  install   full install (default)
  sync      install only what is missing for the selected WM(s)   <- use after switching i3 <-> sway
  doctor    report present / missing dependencies
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c
from common import (BLUE, BOLD, DIM, GREEN, NC, RED, SYM, YELLOW, InstallError, info, ok, panel,
                    run, warn)

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
def step_python_env(backend) -> None:
    py = c.VENV_DIR / "bin" / "python"
    if not c.VENV_DIR.exists():
        cmd = [sys.executable, "-m", "venv"]
        if backend.VENV_SYSTEM_SITE:
            cmd.append("--system-site-packages")  # see python-gobject from pacman
        run(cmd + [c.VENV_DIR], label="Creating virtual environment")
    run([py, "-m", "pip", "install", "--upgrade", "pip"], label="Upgrading pip")
    req = c.INSTALL_DIR / "requirements.txt"
    if req.exists():
        run([py, "-m", "pip", "install", "-r", req], label="Installing Python requirements")
    else:
        warn("requirements.txt not found, skipping Python deps.")


def step_fonts() -> None:
    font_dir = c.HOME / ".local" / "share" / "fonts" / c.SHELL_NAME
    font_dir.mkdir(parents=True, exist_ok=True)
    fetched = False
    for name, url in FONTS.items():
        if (font_dir / name).exists():
            continue
        fetched = True
        print("  {} Downloading {}".format(SYM["dot"], name))
        c.download(url, font_dir / name)
    if fetched:
        run(["fc-cache", "-f"], label="Updating font cache")
    else:
        ok("Fonts present.")


def step_launchers() -> Path:
    c.BIN_DIR.mkdir(parents=True, exist_ok=True)
    main_launcher = c.BIN_DIR / c.SHELL_NAME
    main_launcher.write_text(
        "#!/usr/bin/env bash\n"
        f'cd "{c.INSTALL_DIR}" || exit 1\n'
        "# one-line hint if the current WM needs dependencies that are not installed yet\n"
        'python3 installer/main.py doctor --quiet || true\n'
        f'"{c.VENV_DIR}/bin/python" main.py "$@" &\n'
        "disown\n")
    setup_launcher = c.BIN_DIR / (c.SHELL_NAME + "-setup")
    setup_launcher.write_text(
        f'#!/usr/bin/env bash\nexec python3 "{c.INSTALL_DIR}/installer/main.py" "$@"\n')
    for p in (main_launcher, setup_launcher):
        p.chmod(0o755)
    ok(f"Launchers: {main_launcher.name}, {setup_launcher.name}")
    return main_launcher


def step_bootstrap(plan) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(c.INSTALL_DIR)
    env["ZENITH_WM"] = ",".join(plan.wms)            # e.g. "i3,sway" – lets config.bootstrap write the right snippets
    env["ZENITH_FEATURES"] = ",".join(plan.features)
    run([c.VENV_DIR / "bin" / "python", "-m", "config.bootstrap"], cwd=c.INSTALL_DIR, env=env,
        label="Running Zenith bootstrap")


# ----------------------------------------------------------------------------
# Pre-flight stage
# ----------------------------------------------------------------------------
def report_problems(problems) -> None:
    lines = []
    for p in problems:
        lines.append("{}{}{} {}".format(RED, SYM["err"], NC, p.msg))
        for h in p.hint.splitlines():
            lines.append(f"    {DIM}{h}{NC}")
    panel("%d problem%s found – stopped before installing anything" % (len(problems), "" if len(problems) == 1 else "s"),
          lines, RED)


def preflight_stage(backend, plan, command):
    c.step("Pre-flight checks")
    if plan.needs_work and not c.OPTS.dry_run:
        c.ensure_sudo()
        backend.prepare()
    problems = backend.preflight(plan, command)

    fixable = [p for p in problems if p.fix]
    if fixable and not c.OPTS.dry_run:
        lines = ["{} {}".format(SYM["dot"], p.msg) for p in fixable] + [""]
        lines += ["{} will {}".format(SYM["dot"], p.fix_desc) for p in fixable]
        panel("Missing prerequisites I can install for you", lines, YELLOW)
        if c.confirm("Install them now?"):
            for p in fixable:
                p.fix()
            plan = backend.plan(plan.wms)
            problems = backend.preflight(plan, command)

    if problems:
        report_problems(problems)
        raise SystemExit(1)
    ok("All checks passed – nothing should surprise you later.")
    return plan


def show_plan(plan, backend) -> None:
    lines = ["WM(s)      : {}".format(", ".join(plan.wms)),
             f"Distro     : {backend.pretty}",
             "Packages   : %d to install (%d already present)" % (len(plan.missing_pkgs), len(plan.pkgs) - len(plan.missing_pkgs))]
    if plan.missing_pkgs:
        lines.append("             {}{}{}".format(DIM, " ".join(plan.missing_pkgs), NC))
    if plan.tools:
        lines.append("Build      : {}".format(", ".join(t.name for t in plan.tools)))
    panel("Plan", lines)


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cmd_doctor(args, backend) -> int:
    quiet = args.quiet
    wms = c.resolve_wms(args.wm, interactive=not quiet)
    if not wms:
        return 0
    plan = backend.plan(wms)
    healthy = not plan.needs_work
    if quiet:
        if not healthy:
            what = list(plan.missing_pkgs) + [t.name for t in plan.tools]
            print("zenith-shell: missing dependencies for {} ({}). Run: zenith-shell-setup sync".format("+".join(wms), ", ".join(what[:4]) + (" ..." if len(what) > 4 else "")), file=sys.stderr)
        return 0 if healthy else 1

    lines = []
    for f in plan.features:
        pk = backend.PACKAGES.get(f, [])
        miss = [p for p in pk if p in plan.missing_pkgs]
        mark = "{}{}{}".format(GREEN, SYM["ok"], NC) if not miss else "{}{}{}".format(RED, SYM["err"], NC)
        lines.append("%s %-8s %d/%d packages" % (mark, f, len(pk) - len(miss), len(pk)))
        if miss:
            lines.append("    {}missing: {}{}".format(DIM, " ".join(miss), NC))
    for t in backend.TOOLS:
        if t.feature in plan.features:
            present = t not in plan.tools
            lines.append("{}{}{} tool: {}".format(GREEN if present else RED, SYM["ok"] if present else SYM["err"], NC, t.name))
    lines.append("%s%s%s virtualenv" % ((GREEN, SYM["ok"], NC) if c.VENV_DIR.exists() else (RED, SYM["err"], NC)))
    panel("Doctor – {}".format("+".join(wms)), lines, GREEN if healthy and c.VENV_DIR.exists() else YELLOW)
    if not healthy:
        info("Fix with:  zenith-shell-setup sync --wm %s" % ("both" if len(wms) > 1 else wms[0]))
    return 0 if healthy else 1


def notices(plan) -> None:
    for wm in plan.wms:
        panel(f"{wm} keybindings",
              [f"{c.SHELL_NAME} has added {wm} config snippets and keybindings.",
               "If you already have custom keybindings you may see duplicate-binding",
               f"warnings. Review: ~/.config/{wm}/config (or your included files)"], YELLOW)
    if "x11" in plan.features:
        panel("Picom (compositor)",
              [f"Config shipped in: {c.INSTALL_DIR}/config/picom",
               "Needs upstream picom v12+; older / distro-patched builds using legacy",
               "syntax may warn or lose effects: https://github.com/yshui/picom"] +
              ([] if c.have("picom") else ["", "Picom is not installed – compositor effects are disabled by default."]),
              YELLOW)
    if str(c.BIN_DIR) not in c.ORIGINAL_PATH.split(":"):
        panel("Action required", [f"{c.BIN_DIR} is not in your PATH. Add to ~/.bashrc / ~/.zshrc:",
                                  "",
                                  '  export PATH="$HOME/.local/bin:$PATH"'], YELLOW)


def cmd_install_or_sync(args, backend, command) -> int:
    started = time.time()
    if command == "sync" and not c.INSTALL_DIR.exists():
        raise InstallError("Zenith Shell is not installed yet – run `install.sh` first.")

    wms = c.resolve_wms(args.wm)
    if not wms:
        raise InstallError("Could not detect i3 or sway. Re-run with --wm i3|sway|both.")

    print(BLUE + (LOGO if command == "install" else "") + NC, end="")
    panel("Zenith Shell – {}{}".format(command, " (dry run)" if args.dry_run else ""),
          [f"Distro  : {backend.pretty}", "WM(s)   : {}".format(", ".join(wms)), f"Log     : {c.LOG_FILE}"])

    plan = backend.plan(wms)
    steps = []
    if plan.missing_pkgs:
        steps.append(("Installing system packages", lambda p: backend.install_packages(p)))
    if plan.tools:
        steps.append(("Building tools from source", lambda p: backend.install_tools(p)))
    if command == "install":
        steps += [("Python environment", lambda p: step_python_env(backend)),
                  ("Fonts", lambda p: step_fonts()),
                  ("Launchers", lambda p: step_launchers()),
                  ("Zenith bootstrap", lambda p: step_bootstrap(p))]

    c.set_total(len(steps) + 1)
    plan = preflight_stage(backend, plan, command)
    show_plan(plan, backend)

    if command == "sync" and not plan.needs_work:
        c.save_state(wms, backend.name)
        ok("Everything for {} is already installed.".format("+".join(wms)))
        return 0
    if args.dry_run:
        info("Dry run – nothing was changed.")
        return 0
    if not c.confirm("Continue?"):
        info("Aborted.")
        return 1

    for title, fn in steps:
        c.step(title)
        fn(plan)

    c.save_state(wms, backend.name)
    print()
    ok(f"Done in {c.fmt_time(time.time() - started)}")
    if command == "install":
        print(BLUE + LOGO + NC)
        print(f"To start, run: {BOLD}zenith-shell{NC}, or restart your session.")
    notices(plan)
    info(f"Switched window manager later? Run: {BOLD}zenith-shell-setup sync{NC}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="install.sh", description="Zenith Shell installer")
    ap.add_argument("command", nargs="?", default="install", choices=["install", "sync", "doctor"])
    ap.add_argument("--wm", default="auto", choices=["auto", "i3", "sway", "both"])
    ap.add_argument("--distro", choices=["arch", "ubuntu"], default=os.environ.get("ZENITH_DISTRO"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true")
    ap.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    c.OPTS.yes, c.OPTS.dry_run = args.yes, args.dry_run

    try:
        backend = load_backend(args.distro or c.detect_distro())
        if args.command == "doctor":
            return cmd_doctor(args, backend)
        return cmd_install_or_sync(args, backend, args.command)
    except InstallError as e:
        panel("Installation failed", [str(e), "", "Completed work is detected automatically,",
                                      "so after fixing the cause just run the same command again."], RED)
        return 1
    except KeyboardInterrupt:
        print("\n" + YELLOW + "Interrupted." + NC)
        return 130
    except subprocess.CalledProcessError as e:
        c.err(f"Command failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())