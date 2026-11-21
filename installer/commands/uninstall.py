import os
import shutil
from pathlib import Path

from installer.paths import (
    BIN_DIR,
    COMPLETIONS,
    CONFIG_DIR,
    FONT_DIR,
    HOME,
    INSTALL_DIR,
    LOG_FILE,
    SHELL_NAME,
    STATE_FILE,
)
from installer.state import load_state
from installer.system import InstallError, ensure_sudo, git_out, have, run, stop_shell
from installer.ui import (
    BLUE,
    DIM,
    NC,
    OPTS,
    RED,
    SYM,
    YELLOW,
    confirm,
    info,
    ok,
    panel,
    set_total,
    step,
)
from installer.wm import WM_FEATURE


def scan_wm_configs() -> list[Path]:
    """Files in the WM configs that mention zenith or link into the install dir.
    These belong to the user: we list them for manual cleanup and never delete them."""
    found: list[Path] = []
    install = Path(os.path.realpath(INSTALL_DIR))
    for wm in WM_FEATURE:
        for dirpath, dirnames, filenames in os.walk(HOME / ".config" / wm):
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
    if INSTALL_DIR.is_symlink() or not (INSTALL_DIR / ".git").is_dir():
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
    resolved, home = path.resolve(), HOME.resolve()
    if resolved == home or resolved in home.parents:
        raise InstallError(
            f"Refusing to remove {path}: it is your home directory or above."
        )
    is_install_dir = (
        resolved == INSTALL_DIR.resolve()
        and (resolved / "installer" / "main.py").is_file()
    )
    if not (is_install_dir or path.name == SHELL_NAME):
        raise InstallError(f"Refusing to remove {path}: not a Zenith Shell directory.")
    try:
        shutil.rmtree(path)
    except PermissionError:  # e.g. files left root-owned by `sudo ninja install`
        ensure_sudo()
        run(
            ["rm", "-rf", "--one-file-system", "--", resolved],
            sudo=True,
            label=f"Removing {path} (root-owned files)",
        )


def cmd_uninstall(args, backend) -> int:
    state = load_state()
    config = CONFIG_DIR / "config.json"
    launchers = [
        p
        for p in (BIN_DIR / SHELL_NAME, BIN_DIR / f"{SHELL_NAME}-setup")
        if p.exists() or p.is_symlink()
    ]
    completions = [target for _, target in COMPLETIONS.values() if target.exists()]
    if not (INSTALL_DIR.exists() or launchers or FONT_DIR.exists() or state):
        info("Nothing to uninstall.")
        return 0

    built = list(state.get("tools", []))
    mentions = scan_wm_configs()
    local_work = has_local_work()
    if local_work and OPTS.yes:
        raise InstallError(
            f"{INSTALL_DIR} has local edits or unpushed commits. "
            "Re-run without --yes to confirm deleting them."
        )
    dot = SYM["dot"]

    purge = args.purge
    if built and not purge and not args.dry_run and not OPTS.yes:
        # Built tools can't be tracked once state is deleted, so ask now.
        # Default No: other Fabric-based shells may use them.
        purge = confirm(
            f"Also remove tools built from source ({', '.join(built)})? "
            "Other Fabric-based shells may use them.",
            default=False,
        )

    lines = [f"{dot} stop running Zenith Shell processes"]
    if INSTALL_DIR.is_symlink():
        lines.append(f"{dot} delete the {INSTALL_DIR} symlink (its target is kept)")
    else:
        lines.append(
            f"{dot} delete {INSTALL_DIR} (code, virtualenv, vendored sources)"
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
    if built and purge:
        lines.append(f"{dot} remove tools built from source: {', '.join(built)}")
    elif built:
        lines.append(
            f"{DIM}Tools built from source are kept ({', '.join(built)}); "
            f"other Fabric-based shells may use them. To remove them, use --purge: "
            f"they can't be tracked after this uninstall.{NC}"
        )
    lines.append(f"{DIM}System packages are never removed automatically.{NC}")
    panel("Uninstall plan", lines, YELLOW)

    if args.dry_run:
        info("Dry run: nothing was changed.")
        return 0

    keep_config = not CONFIG_DIR.exists() or confirm(
        f"Keep your settings and agenda ({CONFIG_DIR})?", default=True
    )
    if not confirm("Uninstall Zenith Shell now?", default=False):
        info("Aborted.")
        return 1

    def stop_processes() -> None:
        ok("Stopped running instances" if stop_shell() else "Nothing was running")

    def remove_built_tools() -> None:
        if any(name != "matugen" for name in built):
            ensure_sudo()
        backend.uninstall_tools(built)

    def remove_launchers() -> None:
        for path in [*launchers, *completions]:
            path.unlink(missing_ok=True)
        ok("Removed launchers and tab completion")

    def remove_fonts() -> None:
        remove_tree(FONT_DIR)
        if have("fc-cache"):
            run(["fc-cache", "-f"], check=False, label="Updating font cache")

    steps = [("Stopping Zenith Shell", stop_processes)]
    # needs vendors/, so before the install dir goes
    if purge and built:
        steps.append(("Removing source-built tools", remove_built_tools))
    steps += [
        ("Removing launchers", remove_launchers),
        ("Removing fonts", remove_fonts),
        ("Removing Zenith Shell", lambda: remove_tree(INSTALL_DIR)),
    ]
    if not keep_config:
        steps.append(
            ("Removing your settings and agenda", lambda: remove_tree(CONFIG_DIR))
        )
    steps += [
        (
            "Cleaning up",
            lambda: [remove_tree(STATE_FILE.parent), remove_tree(LOG_FILE.parent)],
        ),
    ]

    set_total(len(steps))
    for title, fn in steps:
        step(title)
        fn()

    print()
    ok("Zenith Shell has been removed.")
    if keep_config and config.exists():
        info(f"Your settings and agenda are kept in {config}.")
    if mentions:
        panel(
            "Leftover references: edit these by hand",
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
                f"{DIM}Other software may depend on these. Review before removing:{NC}",
                "",
                f"{backend.REMOVE_CMD} {' '.join(pkgs)}",
            ],
            BLUE,
        )
    return 0
