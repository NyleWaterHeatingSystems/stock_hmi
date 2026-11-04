#!/usr/bin/env python3
"""Tests for hpc-usb-update.py: no root, no drive and no systemd needed.

Every path the updater touches is moved into a temporary directory, and
systemctl, chown and mount are replaced. A "drive" is a plain directory.

Usage: python3 tests/test_usb_update.py
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parent.parent / "hpc-usb-update.py"
spec = importlib.util.spec_from_file_location("hpc_usb_update", SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assets_hash_like_create_release(release: Path) -> str:
    """The exact pipeline in HPC_Firmware tools/create_release.sh."""
    command = ("find assets -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum "
               "| awk '{print $1}'")
    return subprocess.run(["bash", "-c", command], cwd=release, check=True, text=True,
                          capture_output=True).stdout.strip()


def make_release(drive: Path, name: str, current: str | None = None, **manifest_changes) -> Path:
    release = drive / "releases" / "versions" / name
    (release / "assets" / "Fonts").mkdir(parents=True)
    (release / "assets" / "Fonts" / "a b.sif").write_bytes(b"font " + name.encode())
    (release / "assets" / "beep.wav").write_bytes(b"sound")
    binary, service, rules = b"app " + name.encode(), b"[Service]\n# " + name.encode(), b"rules " + name.encode()
    (release / f"hmi_{name}.bin").write_bytes(binary)
    (release / "hmi.service").write_bytes(service)
    (release / "hmi-networkmanager.rules").write_bytes(rules)
    manifest = {
        "release_version": name,
        "source_commit": "abc123",
        "requires_setup": None,
        "debs": None,
        "components": {
            "hmi": {"file": f"hmi_{name}.bin", "sha256": sha256(binary)},
            "hmi_service": {"file": "hmi.service", "sha256": sha256(service)},
            "hmi_polkit_rules": {"file": "hmi-networkmanager.rules", "sha256": sha256(rules)},
            "assets": {"dir": "assets", "sha256": assets_hash_like_create_release(release)},
        },
    }
    manifest.update(manifest_changes)
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (drive / "releases" / "CURRENT").write_text((current or name) + "\n", encoding="utf-8")
    return release


class FakeSystem:
    """Stands in for systemctl and friends, and records what was asked."""

    def __init__(self, healthy=True):
        self.commands = []
        self.healthy = healthy
        self.started = 0
        self.app_running_at_start = []

    def run(self, command, *, check=True):
        self.commands.append(command)
        stdout = ""
        if command[:2] == ["systemctl", "start"]:
            self.started += 1
            self.app_running_at_start.append(
                (updater.APP_DIR / "release-manifest.json").read_text(encoding="utf-8"))
        if command[:2] == ["systemctl", "show"]:
            calls = sum(1 for c in self.commands if c[:2] == ["systemctl", "show"])
            restarts = 0 if self.healthy or calls == 1 else 3
            stdout = f"ActiveState=active\nNRestarts={restarts}\n"
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class UpdateTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="usb-update-"))
        self.addCleanup(shutil.rmtree, self.root)
        self.drive = self.root / "drive"
        self.drive.mkdir()
        self.saved = {}
        hmi = self.root / "home"
        paths = {
            "APP_DIR": hmi / "bin",
            "PREVIOUS_APP_DIR": hmi / "bin.previous",
            "SERVICE_FILE": self.root / "etc" / "hmi.service",
            "POLKIT_RULES_FILE": self.root / "etc" / "50-hpc-hmi-networkmanager.rules",
            "RELEASE_INFO_FILE": self.root / "etc" / "hpc-release",
            "UPDATE_DIR": self.root / "update",
            "STAGE_DIR": self.root / "update" / "stage",
            "PREVIOUS_SYSTEM_DIR": self.root / "update" / "previous-system",
            "APPLYING_MARKER": self.root / "update" / "applying",
            "LOCK_FILE": self.root / "update" / "lock",
            "RUN_DIR": self.root / "run",
            "STATUS_FILE": self.root / "run" / "status.json",
            "INSTALL_REQUEST": self.root / "run" / "install",
            "MOUNT_DIR": self.root / "run" / "mount",
        }
        for name, value in paths.items():
            self.patch(name, value)
        self.patch("HEALTH_CHECK_SECONDS", 0.05)
        self.patch("APP_USER", "root" if os.getuid() == 0 else self.current_user())
        self.patch("set_owner", lambda path: None)
        self.patch("show_on_console", lambda text: None)
        self.system = FakeSystem()
        self.patch("run", self.system.run)
        real_sleep = updater.time.sleep
        self.addCleanup(setattr, updater.time, "sleep", real_sleep)
        updater.time.sleep = lambda seconds: None
        os_chown = updater.os.chown
        self.addCleanup(setattr, updater.os, "chown", os_chown)
        updater.os.chown = lambda *args: None
        (self.root / "etc").mkdir()
        updater.UPDATE_DIR.mkdir()
        self.install("v2.0.10", settings=b"unit 4 settings")
        updater.RELEASE_INFO_FILE.write_text("HPC_SETUP=setup-v1.1.0\nHPC_APP=v2.0.10\nHPC_GOLDEN=x\n")

    @staticmethod
    def current_user():
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name

    def patch(self, name, value):
        self.addCleanup(setattr, updater, name, getattr(updater, name))
        setattr(updater, name, value)

    def install(self, name, settings=None):
        updater.APP_DIR.mkdir(parents=True)
        (updater.APP_DIR / "HPC_LinuxGUI").write_bytes(b"app " + name.encode())
        (updater.APP_DIR / "release-manifest.json").write_text(json.dumps({"release_version": name}))
        if settings:
            (updater.APP_DIR / "settings.txt").write_bytes(settings)
        updater.SERVICE_FILE.write_text("old service")
        updater.POLKIT_RULES_FILE.write_text("old rules")

    def status(self):
        return json.loads(updater.STATUS_FILE.read_text())

    def stage(self):
        updater.stage_release(self.drive)

    def scan(self):
        """stage_release with the error handling --scan gives it."""
        self.patch("mount_drive", lambda device: (self.drive, False))
        return updater.scan(Path("/dev/fake"))


class Staging(UpdateTestCase):
    def test_drive_without_releases_is_ignored(self):
        (self.drive / "HPC_LOGS").mkdir()
        self.scan()
        self.assertFalse(updater.STATUS_FILE.exists())
        self.assertIsNone(updater.stage_ready())

    def test_newer_release_is_offered(self):
        make_release(self.drive, "v2.0.11")
        self.stage()
        self.assertEqual(self.status()["state"], "ready")
        self.assertEqual(self.status()["version"], "v2.0.11")
        self.assertEqual(updater.stage_ready(), "v2.0.11")

    def test_same_and_older_are_not_offered(self):
        for name in ("v2.0.10", "v2.0.9", "v2.0.10-RC4"):
            shutil.rmtree(self.drive / "releases", ignore_errors=True)
            make_release(self.drive, name)
            self.stage()
            self.assertFalse(updater.STATUS_FILE.exists(), name)

    def test_current_decides_not_the_highest_folder(self):
        make_release(self.drive, "v2.0.11")
        make_release(self.drive, "v9.0.0-RC1", current="v2.0.11")
        self.stage()
        self.assertEqual(self.status()["version"], "v2.0.11")

    def test_final_release_is_newer_than_its_candidate(self):
        self.assertLess(updater.release_sort_key("v2.1.0-RC2"), updater.release_sort_key("v2.1.0"))
        self.assertLess(updater.release_sort_key("v2.1.0-RC2"), updater.release_sort_key("v2.1.0-RC10"))
        self.assertLess(updater.release_sort_key("v2.0.9"), updater.release_sort_key("v2.0.10"))

    def test_unknown_install_is_offered(self):
        (updater.APP_DIR / "release-manifest.json").unlink()
        make_release(self.drive, "v2.0.11")
        self.stage()
        self.assertEqual(self.status()["state"], "ready")

    def test_requires_setup_is_blocked_before_copying(self):
        make_release(self.drive, "v2.0.11", requires_setup="v2.1.0")
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")
        self.assertIn("full USB kit", self.status()["message"])
        self.assertIsNone(updater.stage_ready())

    def test_corrupt_files_are_refused(self):
        for victim in ("hmi_v2.0.11.bin", "hmi.service", "assets/beep.wav"):
            shutil.rmtree(self.drive / "releases", ignore_errors=True)
            release = make_release(self.drive, "v2.0.11")
            (release / victim).write_bytes(b"corrupted")
            self.scan()
            self.assertEqual(self.status()["state"], "blocked", victim)
            self.assertIsNone(updater.stage_ready(), victim)

    def test_added_asset_is_refused(self):
        release = make_release(self.drive, "v2.0.11")
        (release / "assets" / "extra.bin").write_bytes(b"x")
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")

    def test_old_release_without_system_files_is_refused(self):
        manifest_release = make_release(self.drive, "v2.0.11")
        manifest = json.loads((manifest_release / "manifest.json").read_text())
        del manifest["components"]["hmi_service"]
        (manifest_release / "manifest.json").write_text(json.dumps(manifest))
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")
        self.assertIn("full USB kit", self.status()["message"])

    def test_manifest_cannot_escape_the_release_folder(self):
        release = make_release(self.drive, "v2.0.11")
        manifest = json.loads((release / "manifest.json").read_text())
        manifest["components"]["hmi"]["file"] = "../../../secret"
        (release / "manifest.json").write_text(json.dumps(manifest))
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")

    def test_current_naming_a_missing_release(self):
        (self.drive / "releases").mkdir()
        (self.drive / "releases" / "CURRENT").write_text("v2.0.11\n")
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")

    def test_garbage_is_blocked_not_a_crash(self):
        (self.drive / "releases").mkdir()
        (self.drive / "releases" / "CURRENT").write_text("not a version")
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")
        release = make_release(self.drive, "v2.0.11")
        (release / "manifest.json").write_text("{ broken")
        self.scan()
        self.assertEqual(self.status()["state"], "blocked")

    def test_assets_hash_matches_create_release(self):
        release = make_release(self.drive, "v2.0.11")
        self.assertEqual(updater.assets_sha256(release / "assets"),
                         assets_hash_like_create_release(release))


class Applying(UpdateTestCase):
    def setUp(self):
        super().setUp()
        make_release(self.drive, "v2.0.11")
        self.stage()
        updater.INSTALL_REQUEST.write_text("")

    def test_install(self):
        self.assertEqual(updater.apply_update(), 0)
        self.assertEqual((updater.APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.11")
        self.assertEqual((updater.APP_DIR / "assets" / "beep.wav").read_bytes(), b"sound")
        self.assertEqual(updater.installed_release(), "v2.0.11")
        self.assertEqual(updater.SERVICE_FILE.read_bytes(), b"[Service]\n# v2.0.11")
        self.assertEqual(updater.POLKIT_RULES_FILE.read_bytes(), b"rules v2.0.11")
        self.assertEqual(self.status()["state"], "installed")
        self.assertIn("v2.0.10", self.status()["message"])
        self.assertFalse(updater.INSTALL_REQUEST.exists())
        self.assertFalse(updater.APPLYING_MARKER.exists())
        self.assertIsNone(updater.stage_ready())

    def test_binary_is_executable(self):
        updater.apply_update()
        self.assertTrue(os.access(updater.APP_DIR / "HPC_LinuxGUI", os.X_OK))

    def test_settings_survive(self):
        updater.apply_update()
        self.assertEqual((updater.APP_DIR / "settings.txt").read_bytes(), b"unit 4 settings")

    def test_release_info_keeps_other_lines(self):
        updater.apply_update()
        info = updater.release_info()
        self.assertEqual(info["HPC_APP"], "v2.0.11")
        self.assertEqual(info["HPC_APP_COMMIT"], "abc123")
        self.assertEqual(info["HPC_SETUP"], "setup-v1.1.0")
        self.assertEqual(info["HPC_GOLDEN"], "x")

    def test_order_stop_reload_start(self):
        updater.apply_update()
        names = [" ".join(c[:2]) for c in self.system.commands if c[1] != "show"]
        self.assertEqual(names, ["systemctl stop", "systemctl daemon-reload", "systemctl start"])

    def test_previous_is_kept(self):
        updater.apply_update()
        self.assertEqual((updater.PREVIOUS_APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.10")

    def test_crashing_app_rolls_back(self):
        self.system.healthy = False
        self.assertEqual(updater.apply_update(), 1)
        self.assertEqual((updater.APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.10")
        self.assertEqual((updater.APP_DIR / "settings.txt").read_bytes(), b"unit 4 settings")
        self.assertEqual(updater.SERVICE_FILE.read_text(), "old service")
        self.assertEqual(updater.POLKIT_RULES_FILE.read_text(), "old rules")
        self.assertEqual(self.status()["state"], "failed")
        self.assertIn("v2.0.10", self.status()["message"])
        self.assertEqual(updater.release_info()["HPC_APP"], "v2.0.10")
        self.assertFalse(updater.APPLYING_MARKER.exists())
        self.assertEqual(self.system.started, 2)

    def test_second_update_replaces_the_kept_previous(self):
        updater.apply_update()
        shutil.rmtree(self.drive / "releases")
        make_release(self.drive, "v2.0.12")
        self.stage()
        self.assertEqual(updater.apply_update(), 0)
        self.assertEqual((updater.PREVIOUS_APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.11")

    def test_apply_with_nothing_staged_touches_nothing(self):
        updater.clear_stage()
        self.assertEqual(updater.apply_update(), 0)
        self.assertEqual(self.system.commands, [])
        self.assertEqual((updater.APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.10")

    def test_failed_packages_change_nothing(self):
        deb_dir = updater.STAGE_DIR / "debs"
        deb_dir.mkdir()
        (deb_dir / "a.deb").write_bytes(b"x")
        real_run = updater.subprocess.run
        self.addCleanup(setattr, updater.subprocess, "run", real_run)
        updater.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=1, stderr="no", stdout="")
        self.assertEqual(updater.apply_update(), 1)
        self.assertEqual((updater.APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.10")
        self.assertEqual(self.status()["state"], "failed")
        self.assertEqual(self.system.commands, [])


class FindingTheDrive(UpdateTestCase):
    def test_finds_the_mount_from_mountinfo(self):
        line = Path("/proc/self/mountinfo").read_text().splitlines()[0].split()
        major, minor = map(int, line[2].split(":"))
        real_stat = updater.os.stat
        self.addCleanup(setattr, updater.os, "stat", real_stat)
        updater.os.stat = lambda path: types.SimpleNamespace(st_rdev=os.makedev(major, minor))
        self.assertEqual(updater.find_mount(Path("/dev/fake")), Path(line[4]))

    def test_unplugged_drive_is_not_an_error(self):
        self.assertEqual(updater.scan(Path("/dev/no-such-drive")), 0)
        self.assertFalse(updater.STATUS_FILE.exists())


class PowerCuts(UpdateTestCase):
    """Boot after power was lost at each step of apply_update."""

    def setUp(self):
        super().setUp()
        make_release(self.drive, "v2.0.11")
        self.stage()

    def cut_at(self, step):
        """Run apply_update until `step` is reached, then stop as a power cut would."""
        class PowerCut(BaseException):
            pass

        steps = {
            "stop": ("run", lambda c: c[:2] == ["systemctl", "stop"]),
            "after_first_rename": ("rename", lambda p: p == updater.APP_DIR),
            "after_swap": ("copyfile", lambda d: d == updater.SERVICE_FILE),
            "health": ("run", lambda c: c[:2] == ["systemctl", "show"]),
        }
        kind, matches = steps[step]
        real_run, real_copy, real_rename = updater.run, updater.shutil.copyfile, Path.rename

        def run(command, *, check=True):
            if kind == "run" and matches(command):
                raise PowerCut()
            return real_run(command, check=check)

        def copyfile(source, destination, **kwargs):
            if kind == "copyfile" and matches(destination):
                raise PowerCut()
            return real_copy(source, destination, **kwargs)

        def rename(path, target):
            result = real_rename(path, target)
            if kind == "rename" and matches(path):
                raise PowerCut()
            return result

        updater.run, updater.shutil.copyfile = run, copyfile
        Path.rename = rename
        self.addCleanup(setattr, Path, "rename", real_rename)
        self.addCleanup(setattr, updater.shutil, "copyfile", real_copy)
        try:
            with self.assertRaises(PowerCut):
                updater.apply_update()
        finally:
            updater.run, updater.shutil.copyfile = real_run, real_copy
            Path.rename = real_rename
        updater.STATUS_FILE.unlink(missing_ok=True)  # /run doesn't survive
        self.assertEqual(updater.boot(), 0)

    def assert_back_on_previous(self):
        self.assertEqual((updater.APP_DIR / "HPC_LinuxGUI").read_bytes(), b"app v2.0.10")
        self.assertEqual((updater.APP_DIR / "settings.txt").read_bytes(), b"unit 4 settings")
        self.assertEqual(updater.installed_release(), "v2.0.10")
        self.assertEqual(self.status()["state"], "failed")
        self.assertFalse(updater.APPLYING_MARKER.exists())

    def test_before_anything_moved(self):
        self.cut_at("stop")
        self.assert_back_on_previous()

    def test_older_previous_is_not_restored(self):
        updater.PREVIOUS_APP_DIR.mkdir()
        (updater.PREVIOUS_APP_DIR / "HPC_LinuxGUI").write_bytes(b"app v2.0.9")
        self.cut_at("stop")
        self.assert_back_on_previous()

    def test_between_the_two_renames(self):
        self.cut_at("after_first_rename")
        self.assert_back_on_previous()

    def test_after_the_swap(self):
        self.cut_at("after_swap")
        self.assert_back_on_previous()
        self.assertEqual(updater.SERVICE_FILE.read_text(), "old service")

    def test_during_the_health_check(self):
        self.cut_at("health")
        self.assert_back_on_previous()
        self.assertEqual(updater.SERVICE_FILE.read_text(), "old service")

    def test_boot_reoffers_a_staged_release(self):
        updater.STATUS_FILE.unlink()
        updater.boot()
        self.assertEqual(self.status()["state"], "ready")

    def test_clean_boot_says_nothing(self):
        updater.clear_stage()
        updater.STATUS_FILE.unlink()
        updater.boot()
        self.assertFalse(updater.STATUS_FILE.exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
