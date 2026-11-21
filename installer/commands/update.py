import os
import sys

from installer.commands.install import cmd_install_or_sync
from installer.paths import INSTALL_DIR, LOG_FILE
from installer.state import load_state, update_state
from installer.system import InstallError, git_out, run, shell_running
from installer.ui import DIM, NC, RED, SYM, YELLOW, confirm, info, ok, panel, warn


def cmd_update(args, backend) -> int:
    """Pulls, then re-execs the freshly pulled installer (--after-pull) to do the rest
    with the new package lists."""
    if not (INSTALL_DIR / ".git").is_dir():
        raise InstallError(
            f"{INSTALL_DIR} is not a git checkout, so there is nothing to update. Run install.sh instead."
        )
    if args.after_pull:
        return cmd_install_or_sync(args, backend, "update")

    dot = SYM["dot"]
    upstream = git_out("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        raise InstallError(
            "The checkout has no upstream branch (detached HEAD?). "
            f"Fix with: git -C {INSTALL_DIR} checkout main"
        )
    branch = git_out("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main" or upstream != "origin/main":
        raise InstallError(
            f"Updates only follow origin/main, but this checkout is on '{branch}' "
            f"(tracking {upstream}). Nothing was changed."
        )
    suffix = " (dry run)" if args.dry_run else ""
    panel(
        f"Zenith Shell: update{suffix}",
        [
            f"Checkout : {INSTALL_DIR}",
            f"Tracking : {upstream}",
            f"Log      : {LOG_FILE}",
        ],
    )

    git = ["git", "-C", str(INSTALL_DIR)]
    run([*git, "fetch", "--quiet"], label="Fetching latest changes")
    old = git_out("rev-parse", "--short", "HEAD")
    incoming = int(git_out("rev-list", "--count", "HEAD..@{u}") or 0)
    local_ahead = int(git_out("rev-list", "--count", "@{u}..HEAD") or 0)

    if incoming == 0:
        if load_state().get("pending_update"):
            warn("A previous update did not finish. Resuming it.")
            return cmd_install_or_sync(args, backend, "update")
        ok(f"Already up to date ({old}).")
        if local_ahead:
            info(f"You have {local_ahead} local commit(s) that are not on {upstream}.")
        return 0
    if local_ahead:
        raise InstallError(
            f"Your checkout has {local_ahead} local commit(s) not on {upstream}, so it cannot "
            f"fast-forward. Rebase it yourself: git -C {INSTALL_DIR} pull --rebase"
        )

    shown = git_out(
        "log", "--oneline", "--no-decorate", "-n", "12", "HEAD..@{u}"
    ).splitlines()
    lines = [f"{dot} {line}" for line in shown]
    if incoming > len(shown):
        lines.append(f"{DIM}... and {incoming - len(shown)} more{NC}")
    panel(f"{incoming} new commit{'s' if incoming != 1 else ''}", lines)

    # local edits are fine, unless the update touches the same files: then stop
    # before pulling, so no stashes and no conflict markers
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
                f"  git -C {INSTALL_DIR} stash        (re-apply later with: git stash pop)",
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
        info("Dry run: nothing was pulled (only `git fetch` ran).")
        return 0
    if shell_running():
        info(
            "Zenith Shell is running; restart it after the update: zenith-shell restart"
        )
    if not confirm("Update now?"):
        info("Aborted.")
        return 1

    run([*git, "pull", "--ff-only"], label="Pulling changes")
    new = git_out("rev-parse", "--short", "HEAD")
    # cleared once phase 2 succeeds
    update_state(pending_update=True, update_from=old, update_to=new)
    ok(f"Repository updated {old} -> {new}")
    info("Continuing with the new version of the installer...")
    sys.stdout.flush()
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(INSTALL_DIR / "installer" / "main.py"),
            "update",
            "--after-pull",
            "--wm",
            args.wm,
            *(["--yes"] if args.yes else []),
            *(["--verbose"] if args.verbose else []),
        ],
    )
