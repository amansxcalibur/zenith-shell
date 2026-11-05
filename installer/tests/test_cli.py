"""Run with: python3 -m unittest discover -s installer/tests

Nothing here touches a real shell: the launcher runs against stubbed pgrep, pkill and python.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INSTALLER))

import common as c
import main as m

COMPLETION_FILES = [
    INSTALLER / "completions" / source for source, _ in m.COMPLETIONS.values()
]
LAUNCHER_COMMANDS = ["start", "stop", "restart", "status", "lock", "setup", "help"]


def subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )


class CompletionTests(unittest.TestCase):
    def test_every_command_and_option_is_completed(self):
        for path in COMPLETION_FILES:
            text = path.read_text()
            for word in LAUNCHER_COMMANDS:
                self.assertIn(word, text, path.name)
            for name, sub in subparsers(m.build_parser()).items():
                self.assertIn(name, text, path.name)
                for action in sub._actions:
                    if action.help == argparse.SUPPRESS or "-h" in action.option_strings:
                        continue
                    longest = max(action.option_strings, key=len).lstrip("-")
                    self.assertIn(longest, text, f"{path.name}: {name}")

    def complete(self, *words: str) -> list[str]:
        script = (
            f'source "{INSTALLER / "completions" / "zenith-shell.bash"}"\n'
            'COMP_WORDS=(zenith-shell "$@"); COMP_CWORD=$(( $# ))\n'
            'COMPREPLY=(); _zenith_shell; printf "%s\\n" "${COMPREPLY[@]}"\n'
        )
        out = subprocess.run(
            ["bash", "-c", script, "bash", *words],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return out.split()

    def test_bash_completion(self):
        self.assertIn("setup", self.complete(""))
        self.assertIn("restart", self.complete("re"))
        self.assertEqual(self.complete("setup", "sy"), ["sync"])
        self.assertEqual(self.complete("setup", "sync", "--wm", "s"), ["sway"])
        self.assertEqual(self.complete("setup", "uninstall", "--p"), ["--purge"])
        self.assertNotIn("--purge", self.complete("setup", "sync", "--"))


class ArgumentTests(unittest.TestCase):
    def parse(self, *argv: str) -> argparse.Namespace:
        parser = m.build_parser()
        return parser.parse_args(m.normalize_argv(list(argv), parser))

    def test_command_can_come_after_options(self):
        args = self.parse("--wm", "i3", "sync")
        self.assertEqual((args.command, args.wm), ("sync", "i3"))

    def test_handover_from_older_installers_still_parses(self):
        args = self.parse(
            "update", "--after-pull", "--distro", "ubuntu", "--wm", "auto", "--yes"
        )
        self.assertTrue(args.after_pull and args.yes)

    def test_wm_all_means_every_wm(self):
        self.assertEqual(c.resolve_wms("all"), ["i3", "sway"])

    def test_purge_only_applies_to_uninstall(self):
        with self.assertRaises(SystemExit):
            self.parse("sync", "--purge")


class LauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.calls = self.root / "calls"
        self.bin = self.root / "stubs"
        self.venv_bin = self.root / "venv" / "bin"
        self.bin.mkdir()
        self.venv_bin.mkdir(parents=True)
        for name, body in (
            ("pgrep", 'echo pgrep >> "$CALLS"; [ -e "$RUNNING" ] && echo 42'),
            ("pkill", 'echo pkill >> "$CALLS"; [ -e "$RUNNING" ] && rm "$RUNNING"'),
        ):
            self.stub(self.bin / name, body)
        self.stub(self.venv_bin / "python", 'echo "python $* dir=$ZENITH_DIR" >> "$CALLS"')
        self.launcher = self.root / "zenith-shell"
        self.launcher.write_text(
            m.LAUNCHER.replace("@INSTALL_DIR@", str(self.root))
            .replace("@VENV@", str(self.root / "venv"))
            .replace("@PROCESS@", c.SHELL_PROCESS)
        )

    @staticmethod
    def stub(path: Path, body: str) -> None:
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def run_launcher(self, *args: str, running: bool = False):
        marker = self.root / "running"
        if running:
            marker.touch()
        env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "CALLS": str(self.calls),
            "RUNNING": str(marker),
        }
        result = subprocess.run(
            ["bash", str(self.launcher), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        calls = self.calls.read_text() if self.calls.exists() else ""
        return result, calls

    def test_unknown_word_does_not_start_the_shell(self):
        result, calls = self.run_launcher("statsu")
        self.assertEqual(result.returncode, 2)
        self.assertIn("zenith-shell status", result.stderr)
        self.assertNotIn("python", calls)

    def test_start_is_refused_while_running(self):
        result, calls = self.run_launcher(running=True)
        self.assertIn("already running", result.stdout)
        self.assertNotIn("python", calls)

    def test_restart_stops_then_starts(self):
        result, calls = self.run_launcher("restart", running=True)
        self.assertEqual(result.returncode, 0)
        self.assertLess(calls.index("pkill"), calls.index("python main.py"))

    def test_setup_exports_the_install_dir(self):
        _, calls = self.run_launcher("setup", "doctor")
        self.assertIn(f"installer/main.py doctor dir={self.root}", calls)


if __name__ == "__main__":
    unittest.main()
