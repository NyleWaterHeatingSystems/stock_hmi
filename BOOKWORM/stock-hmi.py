#!/usr/bin/env python3
"""Zero-input provisioning for an EDATEC stock OS running HPC_LinuxGUI."""

from __future__ import annotations

import grp
import logging
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time
import traceback
"""
This script assumes a stock OS is pre provissioned with:
Bookworm, Debain 12, and drivers provided
user: pi
pass: raspberry
upon completion, pi user will not exist, replaced by nwhs
The HPC_LinuxGUI is set to run with sudo permissions via setcap
"""

APP_USER = "nwhs"
LEGACY_LOGIN_USERS = ("pi",)
HMI_HOSTNAME = "hpc"
MQTT_HOST = "127.0.0.1"
AUTO_REBOOT = True

# Salted SHA-512 crypt hash for the standard deployment password. The literal
# password is intentionally not stored in this source or the compiled program.
# gen with: openssl passwd -6 <new_password>
APP_PASSWORD_HASH = (
    "$6$qBuEoYkjKWbrHgkX$"
    "v/sS5WyBz7TuryebGPQV6oSSrQ9XWZcpkURMW2UeMsTapJXDK12Xt3ZtzyCXOdSh"
    "Iw1xKqS37Wg/wlI82ouLy0"
)

PACKAGES = (
    "iptables",
    "libpaho-mqtt1.3",
    "libx11-dev",
    "network-manager",
    "openssh-server",
    "rsync",
    "sudo",
)

LOG_FILE = Path("/var/log/hpc-stock-installer.log")


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launcher_command(*extra: str) -> list[str]:
    if frozen():
        return [str(Path(sys.executable).resolve()), *extra]
    return [sys.executable, str(Path(__file__).resolve()), *extra]


def bundle_directory() -> Path:
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def show_notification(title: str, message: str, urgency: str = "normal") -> None:
    notifier = shutil.which("notify-send")
    if not notifier:
        return
    subprocess.run(
        [notifier, f"--urgency={urgency}", title, message],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_own_terminal() -> bool:
    terminal = shutil.which("x-terminal-emulator")
    if not terminal:
        return False
    subprocess.Popen(
        [terminal, "-e", *launcher_command("--terminal")],
        start_new_session=True,
    )
    return True


def elevate_without_prompt() -> int:
    sudo = shutil.which("sudo")
    if not sudo:
        show_notification(
            "HPC installer failed",
            "sudo is not installed on the stock image.",
            "critical",
        )
        return 1

    result = subprocess.run([sudo, "-n", *launcher_command("--as-root")])
    if result.returncode != 0:
        message = (
            "The stock login does not have passwordless sudo. "
            "Automatic provisioning cannot continue."
        )
        print(f"\nERROR: {message}", file=sys.stderr)
        show_notification("HPC installer failed", message, "critical")
        time.sleep(15)
    return result.returncode


def configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        handlers=handlers,
    )


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    logging.info("Running: %s", " ".join(command))
    return subprocess.run(command, check=check, text=True)


def command_path(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required command was not found after package install: {name}")
    return path


def ensure_user() -> None:
    try:
        pwd.getpwnam(APP_USER)
    except KeyError:
        run(
            [
                "useradd",
                "--create-home",
                "--user-group",
                "--shell",
                "/bin/bash",
                APP_USER,
            ]
        )

    supplementary = []
    for group_name in (
        "sudo",
        "video",
        "render",
        "input",
        "dialout",
        "netdev",
        "gpio",
        "i2c",
        "spi",
    ):
        try:
            grp.getgrnam(group_name)
        except KeyError:
            continue
        supplementary.append(group_name)

    if supplementary:
        run(["usermod", "--append", "--groups", ",".join(supplementary), APP_USER])

    run(["usermod", "--shell", "/bin/bash", APP_USER])

    # usermod receives the hash as an argument without invoking a shell.
    run(["usermod", "--password", APP_PASSWORD_HASH, APP_USER])


def install_application(source_dir: Path, app_dir: Path) -> None:
    executable = source_dir / "HPC_LinuxGUI"
    assets = source_dir / "assets"
    if not executable.is_file():
        raise RuntimeError(f"Missing application: {executable}")
    if not assets.is_dir():
        raise RuntimeError(f"Missing assets directory: {assets}")

    app_dir.mkdir(parents=True, exist_ok=True)
    if source_dir.resolve() != app_dir.resolve():
        run(
            [
                command_path("rsync"),
                "-a",
                "--delete",
                f"--chown={APP_USER}:{APP_USER}",
                f"{source_dir}/",
                f"{app_dir}/",
            ]
        )
    run(["chown", "-R", f"{APP_USER}:{APP_USER}", str(app_dir.parent)])
    run(["chmod", "0755", str(app_dir / "HPC_LinuxGUI")])

    dependency_check = subprocess.run(
        [command_path("ldd"), str(app_dir / "HPC_LinuxGUI")],
        check=False,
        capture_output=True,
        text=True,
    )
    logging.info("ldd output:\n%s", dependency_check.stdout.strip())
    combined_output = dependency_check.stdout + dependency_check.stderr
    if dependency_check.returncode != 0 or "not found" in combined_output:
        raise RuntimeError(f"HPC_LinuxGUI dependency check failed:\n{combined_output}")

    installed_executable = app_dir / "HPC_LinuxGUI"
    run(
        [
            command_path("setcap"),
            "cap_net_admin,cap_net_raw+ep",
            str(installed_executable),
        ]
    )

def configure_hostname() -> None:
    run(["hostnamectl", "set-hostname", HMI_HOSTNAME])

    hosts_path = Path("/etc/hosts")
    lines = hosts_path.read_text(encoding="utf-8").splitlines()
    replacement = f"127.0.1.1\t{HMI_HOSTNAME}"
    replaced = False
    updated = []
    for line in lines:
        if not replaced and re.match(r"^\s*127\.0\.1\.1(?:\s|$)", line):
            updated.append(replacement)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.extend(("", replacement))
    hosts_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def configure_sudo_access() -> None:
    # Membership in sudo grants normal administrative access using the nwhs
    # password. HPC_LinuxGUI invokes nmcli without a terminal, so that one
    # command must remain passwordless.
    # Remove the filename used by earlier revisions of this installer.
    Path(f"/etc/sudoers.d/{APP_USER}-networkmanager").unlink(missing_ok=True)

    sudoers = Path(f"/etc/sudoers.d/{APP_USER}-hpc")
    sudoers.write_text(
        f"{APP_USER} ALL=(ALL:ALL) ALL\n"
        f"{APP_USER} ALL=(root) NOPASSWD: {command_path('nmcli')}\n",
        encoding="utf-8",
    )
    sudoers.chmod(0o440)
    run([command_path("visudo"), "--check", "--file", str(sudoers)])

def configure_touchscreen_udev() -> None:
    rules_path = Path("/etc/udev/rules.d/99-touchscreen.rules")
    rules_path.write_text(
        'SUBSYSTEM=="input", KERNEL=="event*", '
        'ENV{ID_INPUT_TOUCHSCREEN}=="1", '
        'SYMLINK+="input/touchscreen", TAG+="systemd"\n',
        encoding="utf-8",
    )

    run(["udevadm", "control", "--reload-rules"])
    run(["udevadm", "trigger", "--subsystem-match=input"])

def configure_legacy_user_cleanup() -> None:
    """Lock old login users now and remove them safely during the reboot."""
    legacy_users = []
    for user_name in LEGACY_LOGIN_USERS:
        if user_name == APP_USER:
            continue
        try:
            pwd.getpwnam(user_name)
        except KeyError:
            continue
        legacy_users.append(user_name)
        run(["usermod", "--lock", user_name])

    cleanup_script = Path("/usr/local/sbin/hpc-remove-legacy-users")
    cleanup_unit = Path("/etc/systemd/system/hpc-remove-legacy-users.service")
    marker = Path("/var/lib/hpc-hmi/remove-legacy-users")

    if not legacy_users:
        marker.unlink(missing_ok=True)
        cleanup_script.unlink(missing_ok=True)
        cleanup_unit.unlink(missing_ok=True)
        run(
            ["systemctl", "disable", "hpc-remove-legacy-users.service"],
            check=False,
        )
        run(["systemctl", "daemon-reload"])
        return

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("\n".join(legacy_users) + "\n", encoding="utf-8")

    cleanup_script.write_text(
        """#!/bin/sh
set -eu

while IFS= read -r user_name; do
    [ -n "$user_name" ] || continue
    if getent passwd "$user_name" >/dev/null; then
        loginctl disable-linger "$user_name" >/dev/null 2>&1 || true
        loginctl terminate-user "$user_name" >/dev/null 2>&1 || true
        pkill -KILL -u "$user_name" >/dev/null 2>&1 || true
        userdel --remove "$user_name"
    fi
done < /var/lib/hpc-hmi/remove-legacy-users

rm -f /var/lib/hpc-hmi/remove-legacy-users
systemctl disable hpc-remove-legacy-users.service >/dev/null 2>&1 || true
""",
        encoding="utf-8",
    )
    cleanup_script.chmod(0o755)

    cleanup_unit.write_text(
        """[Unit]
Description=Remove legacy HPC login users
ConditionPathExists=/var/lib/hpc-hmi/remove-legacy-users
After=local-fs.target systemd-logind.service systemd-user-sessions.service
Before=getty@tty1.service hmi.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/hpc-remove-legacy-users

[Install]
WantedBy=multi-user.target
""",
        encoding="utf-8",
    )

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "hpc-remove-legacy-users.service"])


def configure_boot(app_dir: Path) -> None:
    existing_groups = []
    for group_name in ("video", "render", "input", "dialout", "netdev", "gpio", "i2c", "spi"):
        try:
            grp.getgrnam(group_name)
        except KeyError:
            continue
        existing_groups.append(group_name)
    groups_line = ""
    if existing_groups:
        groups_line = f"SupplementaryGroups={' '.join(existing_groups)}\n"

    console_service_text = f"""[Unit]
Description=Prepare tty1 for the HPC framebuffer HMI
After=getty@tty1.service
Before=hmi.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c '{command_path('chvt')} 1; {command_path('setterm')} --cursor off --blank 0 < /dev/tty1 > /dev/tty1'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
    Path("/etc/systemd/system/hmi-console.service").write_text(
        console_service_text,
        encoding="utf-8",
    )

    service_text = f"""[Unit]
Description=HPC framebuffer HMI
Wants=NetworkManager.service getty@tty1.service hmi-console.service
After=NetworkManager.service getty@tty1.service hmi-console.service systemd-user-sessions.service

[Service]
Type=simple
User=nwhs
Group=nwhs
SupplementaryGroups=video render input dialout netdev gpio i2c spi tty
WorkingDirectory=/home/nwhs/hpc-hmi/bin
Environment=HOME=/home/nwhs
Environment="QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/touchscreen"
Environment="TSLIB_TSDEVICE=/dev/input/touchscreen"
Environment="SDL_MOUSEDEV=/dev/input/touchscreen"
# Turn off cursor, and disable blinks
ExecStartPre=+/bin/sh -c '/usr/bin/setterm --term linux --clear all --cursor off < /dev/tty1 > /dev/tty1'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'
ExecStart=/home/nwhs/hpc-hmi/bin/HPC_LinuxGUI 192.168.0.2
Restart=always
RestartSec=2
StandardInput=null
StandardOutput=journal
StandardError=journal


[Install]
WantedBy=multi-user.target
"""
    Path("/etc/systemd/system/hmi.service").write_text(service_text, encoding="utf-8")

    autologin_dir = Path("/etc/systemd/system/getty@tty1.service.d")
    autologin_dir.mkdir(parents=True, exist_ok=True)
    agetty = shutil.which("agetty") or "/sbin/agetty"
    autologin_text = f"""[Service]
ExecStart=
ExecStart=-{agetty} --autologin {APP_USER} --noclear %I $TERM
"""
    (autologin_dir / "autologin.conf").write_text(autologin_text, encoding="utf-8")

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "ssh.service"])
    run(
        [
            "systemctl",
            "enable",
            "NetworkManager.service",
            "getty@tty1.service",
            "hmi-console.service",
            "hmi.service",
        ]
    )
    run(["systemctl", "disable", "NetworkManager-wait-online.service"], check=False)
    run(["systemctl", "mask", "NetworkManager-wait-online.service"], check=False)
    run(["systemctl", "set-default", "multi-user.target"])
    run(["systemctl", "disable", "display-manager.service"], check=False)


def provision() -> None:
    source_dir = bundle_directory() / "bin"
    app_dir = Path(f"/home/{APP_USER}/hpc-hmi/bin")

    logging.info("Starting stock EDATEC application-layer provisioning")
    logging.info("Application source: %s", source_dir)

    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    logging.info("Installing runtime packages")
    deb_dir = bundle_directory() / "debs"
    deb_files = sorted(deb_dir.glob("*.deb"))

    if not deb_files:
        raise RuntimeError(f"No offline packages found in: {deb_dir}")

    subprocess.run(
        [
            "dpkg",
            "--install",
            *map(str, deb_files),
        ],
        check=True,
        env=env,
    )
    #subprocess.run(["apt-get", "update"], check=True, env=env)
    #subprocess.run(
    #    ["apt-get", "install", "-y", "--no-install-recommends", *PACKAGES],
    #    check=True,
    #    env=env,
    #)

    ensure_user()
    install_application(source_dir, app_dir)
    configure_hostname()
    configure_sudo_access()
    configure_touchscreen_udev()
    configure_boot(app_dir)
    configure_legacy_user_cleanup()

    marker_dir = Path("/var/lib/hpc-hmi")
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "stock-os-provisioned").write_text(
        "EDATEC driver configuration preserved; application layer installed.\n",
        encoding="utf-8",
    )

    logging.info("Provisioning completed successfully")
    logging.info("The system will reboot in five seconds")
    show_notification("HPC installer", "Installation complete; rebooting.")
    time.sleep(5)
    if AUTO_REBOOT:
        run(["systemctl", "reboot", "--no-block"])


def main() -> int:
    arguments = set(sys.argv[1:])

    if os.geteuid() != 0:
        if not sys.stdout.isatty() and "--terminal" not in arguments:
            if open_own_terminal():
                return 0
        return elevate_without_prompt()

    configure_logging()
    try:
        provision()
    except Exception as exc:  # Keep a deployment failure visible and logged.
        logging.error("Provisioning failed: %s", exc)
        logging.error("%s", traceback.format_exc())
        show_notification("HPC installer failed", str(exc), "critical")
        time.sleep(20)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
