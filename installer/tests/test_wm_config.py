import os
import sys
import stat
import atexit
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# keep the writers away from the live session
LIVE_SESSION_VARS = ("SWAYSOCK", "I3SOCK", "HYPRLAND_INSTANCE_SIGNATURE", "ZENITH_BOOTSTRAP_WM")
for name in LIVE_SESSION_VARS:
    os.environ.pop(name, None)
if "config.config" not in sys.modules:
    os.environ["HOME"] = tempfile.mkdtemp(prefix="zenith-test-home-")
    atexit.register(shutil.rmtree, os.environ["HOME"], True)

from loguru import logger

from wm.sway import SwayWM
from wm.hyprland import HyprlandWM
from wm.detect import has_autostart, needs_sync
from wm.i3 import I3WM
from wm.legacy import HEADER as LEGACY_HEADER

from installer.commands import steps

I3_HOOK = "include zenith.d/*.conf"
HYPR_START = 'hl.on("hyprland.start", function() hl.exec_cmd("zenith-shell") end)'
HYPR_REQUIRE = 'pcall(require, "zenith")'
IS_ROOT = os.geteuid() == 0


def count_active(text: str, line: str) -> int:
    return sum(1 for raw in text.splitlines() if raw.strip() == line)


class TempHome(unittest.TestCase):
    def setUp(self):
        logger.disable("wm")
        self.addCleanup(logger.enable, "wm")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {"HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_wm(self, cls):
        wm = cls()
        if isinstance(wm, SwayWM):
            wm._swayfx = False
        wm.config_dir.mkdir(parents=True, exist_ok=True)
        return wm

    def run_startup(self, wm):
        wm.write_autostart()
        wm.write_keybinds()
        wm.write_general()
        wm.write_theme()

    def make_read_only(self, path: Path):
        path.chmod(stat.S_IRUSR)
        self.addCleanup(path.chmod, stat.S_IRUSR | stat.S_IWUSR)


class I3ConfigTests(TempHome):
    WMS = (I3WM, SwayWM)

    def test_startup_never_creates_the_user_config(self):
        for cls in self.WMS:
            with self.subTest(wm=cls.name):
                wm = self.make_wm(cls)
                self.run_startup(wm)
                self.assertFalse(wm.config_path.exists())
                for path in (wm.autostart_conf, wm.keybinds_conf, wm.general_conf, wm.theme_conf):
                    self.assertTrue(path.is_file(), path.name)

    def test_startup_and_update_leave_the_user_config_alone(self):
        for cls in self.WMS:
            with self.subTest(wm=cls.name):
                wm = self.make_wm(cls)
                wm.config_path.write_text("# my own config\n")
                self.run_startup(wm)
                wm.bootstrap()
                self.assertEqual(wm.config_path.read_text(), "# my own config\n")

    def test_install_adds_one_include_after_a_blank_line(self):
        for cls in self.WMS:
            with self.subTest(wm=cls.name):
                wm = self.make_wm(cls)
                wm.config_path.write_text("set $mod Mod4")
                wm.bootstrap(can_edit_user_wm_config=True)
                self.assertEqual(
                    wm.config_path.read_text(),
                    "set $mod Mod4\n\n# Zenith Shell\ninclude zenith.d/*.conf\n",
                )
                self.assertTrue(has_autostart(wm.name))

    def test_install_seeds_a_missing_config(self):
        wm = self.make_wm(I3WM)
        wm.bootstrap(can_edit_user_wm_config=True)
        text = wm.config_path.read_text()
        self.assertEqual(count_active(text, I3_HOOK), 1)

    def test_install_is_idempotent(self):
        wm = self.make_wm(I3WM)
        wm.config_path.write_text("set $mod Mod4\n")
        wm.bootstrap(can_edit_user_wm_config=True)
        first = wm.config_path.read_text()
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertEqual(wm.config_path.read_text(), first)

    def test_install_appends_below_a_commented_include(self):
        wm = self.make_wm(I3WM)
        wm.config_path.write_text(f"set $mod Mod4\n# {I3_HOOK}\n")
        self.assertFalse(has_autostart(wm.name))
        wm.bootstrap(can_edit_user_wm_config=True)
        text = wm.config_path.read_text()
        self.assertIn(f"# {I3_HOOK}\n", text)
        self.assertEqual(count_active(text, I3_HOOK), 1)

    def test_legacy_install_is_migrated(self):
        for cls in self.WMS:
            with self.subTest(wm=cls.name):
                wm = self.make_wm(cls)
                old_dir = wm.config_dir / "conf.d"
                old_dir.mkdir()
                for name in ("keybinds.conf", "general.conf", "borders.conf"):
                    (old_dir / name).write_text(f"{LEGACY_HEADER}\nstuff\n")
                user_bind = "bindsym $mod+x exec zenith-shell settings"
                wm.config_path.write_text(
                    f"set $mod Mod4\n{user_bind}\n"
                    f"# globbing all .conf in /conf.d\ninclude {old_dir}/*.conf\n"
                    f"\n# zenith startup\nexec {wm.exec_flags} zenith-shell\n"
                )
                self.assertFalse(has_autostart(wm.name))
                wm.bootstrap(can_edit_user_wm_config=True)
                self.assertEqual(
                    wm.config_path.read_text(),
                    f"set $mod Mod4\n{user_bind}\n\n# Zenith Shell\n{I3_HOOK}\n",
                )
                self.assertFalse(old_dir.exists())

    def test_leftovers_next_to_the_new_include_still_get_synced(self):
        wm = self.make_wm(I3WM)
        old_dir = wm.config_dir / "conf.d"
        old_dir.mkdir()
        (old_dir / "keybinds.conf").write_text(f"{LEGACY_HEADER}\n")
        wm.config_path.write_text(
            f"set $mod Mod4\n\n# Zenith Shell\n{I3_HOOK}\n"
            f"\n# zenith startup\nexec --no-startup-id zenith-shell\n"
            f"# globbing all .conf in /conf.d\ninclude {old_dir}/*.conf\n"
        )
        self.assertTrue(has_autostart(wm.name))
        self.assertTrue(needs_sync(wm.name))
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertEqual(
            wm.config_path.read_text(), f"set $mod Mod4\n\n# Zenith Shell\n{I3_HOOK}\n"
        )
        self.assertFalse(old_dir.exists())
        self.assertFalse(needs_sync(wm.name))

    def test_migration_keeps_conf_d_with_user_files(self):
        wm = self.make_wm(I3WM)
        old_dir = wm.config_dir / "conf.d"
        old_dir.mkdir()
        (old_dir / "keybinds.conf").write_text(f"{LEGACY_HEADER}\n")
        (old_dir / "mine.conf").write_text("# mine\n")
        old_include = f"# globbing all .conf in /conf.d\ninclude {old_dir}/*.conf\n"
        wm.config_path.write_text(f"set $mod Mod4\n{old_include}")
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertIn(old_include, wm.config_path.read_text())
        self.assertEqual([p.name for p in old_dir.iterdir()], ["mine.conf"])

    def test_migration_handles_a_removed_blank_line(self):
        wm = self.make_wm(I3WM)
        wm.config_path.write_text("set $mod Mod4\n# zenith startup\nexec --no-startup-id zenith-shell\n")
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertEqual(wm.config_path.read_text(), f"set $mod Mod4\n\n# Zenith Shell\n{I3_HOOK}\n")

    def test_autostart_steps_aside_for_the_users_own_exec(self):
        wm = self.make_wm(I3WM)
        wm.config_path.write_text("set $mod Mod4\n")
        wm.write_autostart()
        self.assertTrue(wm.autostart_conf.read_text().endswith("\nexec --no-startup-id zenith-shell\n"))
        wm.config_path.write_text("set $mod Mod4\nexec --no-startup-id zenith-shell\n")
        wm.write_autostart()
        self.assertTrue(wm.autostart_conf.read_text().endswith("\n# exec --no-startup-id zenith-shell\n"))

    def test_has_autostart_only_counts_an_active_include(self):
        wm = self.make_wm(I3WM)
        cases = {
            f"{I3_HOOK}\n": True,
            "  include ~/.config/i3/zenith.d/*.conf\n": True,
            f"# {I3_HOOK}\n": False,
            "exec --no-startup-id zenith-shell\n": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                wm.config_path.write_text(text)
                self.assertIs(has_autostart(wm.name), expected)

    @unittest.skipIf(IS_ROOT, "root can write read-only files")
    def test_read_only_config_warns_and_keeps_going(self):
        wm = self.make_wm(I3WM)
        wm.config_path.write_text("# read only\n")
        self.make_read_only(wm.config_path)
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertEqual(wm.config_path.read_text(), "# read only\n")
        self.assertTrue(wm.keybinds_conf.is_file())

    @unittest.skipIf(IS_ROOT, "root can write read-only dirs")
    def test_unwritable_zenith_d_does_not_raise(self):
        wm = self.make_wm(I3WM)
        wm.glob_dir.mkdir()
        self.make_read_only(wm.glob_dir)
        wm.glob_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.run_startup(wm)


class HyprlandConfigTests(TempHome):
    def test_startup_never_creates_the_user_config(self):
        wm = self.make_wm(HyprlandWM)
        self.run_startup(wm)
        self.assertFalse(wm.config_path.exists())
        self.assertTrue(wm.generated_path.is_file())

    def test_startup_creates_the_hypr_dir_for_zenith_lua(self):
        wm = HyprlandWM()
        wm.write_keybinds()
        self.assertTrue(wm.generated_path.is_file())
        self.assertFalse(wm.config_path.exists())

    def test_startup_and_update_leave_the_user_config_alone(self):
        wm = self.make_wm(HyprlandWM)
        wm.config_path.write_text("-- mine\n")
        self.run_startup(wm)
        wm.bootstrap()
        self.assertEqual(wm.config_path.read_text(), "-- mine\n")

    def test_install_adds_only_the_missing_active_lines(self):
        cases = {
            "fresh": ("-- mine\n", True),
            "commented": (f"-- mine\n-- {HYPR_START}\n-- {HYPR_REQUIRE}\n", True),
            "hooked": (f"-- mine\n{HYPR_START}\n{HYPR_REQUIRE}\n", False),
            "require removed": (f"-- mine\n{HYPR_START}\n", True),
        }
        for label, (text, changes) in cases.items():
            with self.subTest(case=label):
                wm = self.make_wm(HyprlandWM)
                wm.config_path.write_text(text)
                wm.bootstrap(can_edit_user_wm_config=True)
                result = wm.config_path.read_text()
                self.assertEqual(count_active(result, HYPR_START), 1)
                self.assertEqual(count_active(result, HYPR_REQUIRE), 1)
                self.assertEqual(result != text, changes)
                self.assertTrue(result.startswith(text))
                wm.bootstrap(can_edit_user_wm_config=True)
                self.assertEqual(wm.config_path.read_text(), result)

    def test_install_never_creates_lua_next_to_a_conf(self):
        wm = self.make_wm(HyprlandWM)
        (wm.config_dir / "hyprland.conf").write_text("# conf\n")
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertFalse(wm.config_path.exists())

    def test_has_autostart_ignores_binds_and_comments(self):
        wm = self.make_wm(HyprlandWM)
        cases = {
            f"{HYPR_START}\n": True,
            f"-- {HYPR_START}\n": False,
            'hl.bind("SUPER + x", hl.dsp.exec_cmd("zenith-shell settings"))\n': False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                wm.config_path.write_text(text)
                self.assertIs(has_autostart(wm.name), expected)

    @unittest.skipIf(IS_ROOT, "root can write read-only files")
    def test_read_only_config_warns_and_keeps_going(self):
        wm = self.make_wm(HyprlandWM)
        wm.config_path.write_text("-- read only\n")
        self.make_read_only(wm.config_path)
        wm.bootstrap(can_edit_user_wm_config=True)
        self.assertEqual(wm.config_path.read_text(), "-- read only\n")
        self.assertTrue(wm.generated_path.is_file())


class InstallerHandoffTests(TempHome):
    def test_step_bootstrap_only_passes_the_flag_when_asked(self):
        for allowed in (False, True):
            with self.subTest(allowed=allowed), mock.patch.object(steps, "run") as run:
                steps.step_bootstrap(["i3"], can_edit_user_wm_config=allowed)
                cmd = [str(part) for part in run.call_args.args[0]]
                self.assertEqual("--edit-user-wm-config" in cmd, allowed)

    def test_bootstrap_entry_point_respects_the_flag(self):
        config = self.home / ".config/i3/config"
        config.parent.mkdir(parents=True)
        config.write_text("set $mod Mod4\n")
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in LIVE_SESSION_VARS
        }
        env.update(HOME=str(self.home), PYTHONPATH=str(ROOT), ZENITH_BOOTSTRAP_WM="i3")

        def bootstrap(*flags):
            subprocess.run(
                [sys.executable, "-m", "config.bootstrap", *flags],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )

        bootstrap()
        self.assertEqual(config.read_text(), "set $mod Mod4\n")
        self.assertTrue((config.parent / "zenith.d/keybinds.conf").is_file())
        bootstrap("--edit-user-wm-config")
        self.assertEqual(count_active(config.read_text(), I3_HOOK), 1)


if __name__ == "__main__":
    unittest.main()
