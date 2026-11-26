import os

from installer.commands.steps import FONTS
from installer.paths import BIN_DIR, FONT_DIR, INSTALL_DIR, ORIGINAL_PATH, SHELL_NAME
from installer.system import InstallError, have, venv_ok
from installer.ui import DIM, GREEN, NC, YELLOW, info, mark, panel
from installer.wm import (
    CONFLICT_FIX,
    conflict_lines,
    keybinding_conflicts,
    resolve_wms,
)

from wm.detect import has_autostart


def cmd_doctor(args, backend) -> int:
    wms = resolve_wms(args.wm)
    if not wms:
        raise InstallError(
            "Could not detect i3, sway or Hyprland. "
            "Re-run with --wm i3|sway|hyprland|all."
        )
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

    launcher = BIN_DIR / SHELL_NAME
    on_path = str(BIN_DIR) in ORIGINAL_PATH.split(":")
    unconfigured = [wm for wm in wms if have(wm) and not has_autostart(wm)]
    not_installed = [wm for wm in wms if not have(wm)]
    conflicts = keybinding_conflicts(wms)
    setup_checks = {
        "virtualenv": venv_ok(),
        "launcher": os.access(launcher, os.X_OK),
        "fonts": all((FONT_DIR / name).exists() for name in FONTS),
    }
    for name, good in setup_checks.items():
        lines.append(f"{mark(good)} {name}")
    lines.append(f"{mark(on_path)} {BIN_DIR} in PATH")
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
        fixes.append(f"{INSTALL_DIR}/installer/install.sh --wm {target}")
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

    panel(f"Doctor: {'+'.join(wms)}", lines, YELLOW if fixes else GREEN)
    for fix in fixes:
        info(f"Fix with:  {fix}")
    return 1 if fixes else 0
