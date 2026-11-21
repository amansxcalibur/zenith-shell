import argparse
import difflib
import os
import sys

from installer.backends import load_backend
from installer.commands.doctor import cmd_doctor
from installer.commands.install import cmd_install_or_sync
from installer.commands.logs import cmd_logs
from installer.commands.uninstall import cmd_uninstall
from installer.commands.update import cmd_update
from installer.system import InstallError, detect_distro
from installer.ui import NC, OPTS, RED, YELLOW, choose, panel


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
        picked = choose("What do you want to do?", names)
        if picked is None:
            parser.print_help()
            return 0
        args = parser.parse_args([picked])

    OPTS.yes = getattr(args, "yes", False)
    OPTS.dry_run = getattr(args, "dry_run", False)
    OPTS.verbose = getattr(args, "verbose", False)

    try:
        if args.command == "logs":
            return cmd_logs(args)
        backend = load_backend(detect_distro())
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
            [str(exc), "", "Fix the cause and run it again, finished steps are skipped."],
            RED,
        )
        return 1
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{NC}")
        return 130
