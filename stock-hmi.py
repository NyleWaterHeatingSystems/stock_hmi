#!/usr/bin/env python3
"""Provision an ED-HMI2220-070C flashed with the golden image as an HPC HMI."""

from __future__ import annotations
import argparse
import grp
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time
import traceback
"""
Runs on the HMI as root, from a kit built by make-usb-kit.py (bin/, system/,
debs/ and hpc-usb-update.py next to this script). It assumes the golden image (see
HOWTO_golden_image.md): Bookworm (Debian 12) Lite with EDATEC's kernel and
drivers, and a login user with passwordless sudo (pi on the golden image).
Upon completion, every regular login user other than nwhs is removed.
"""

APP_USER = "nwhs"
# Debian's range for regular (human) login accounts; see UID_MIN/UID_MAX
# in /etc/login.defs. System accounts and nobody (65534) fall outside it.
REGULAR_UID_RANGE = range(1000, 60000)
HMI_HOSTNAME = "hpc"
# NetworkManager profiles: (name, port, initial address). The app rewrites
# eth1-mcp's address to 192.168.1.(unit number + 1)/24; .2 is unit 1.
# A port is an interface name, or a udev ID_PATH ("platform-...") to match the
# socket by hardware path. eth1 and eth2 are two r8152 USB NICs whose names
# follow USB enumeration order, so they are matched by path; eth0 is the CM4's
# own bcmgenet port. Paths checked on a panel with udevadm ID_PATH on the MCP
# and BMS sockets (HOWTO_golden_image.md, 1.5).
USB_PORT_PATH = "platform-fd500000.pcie-pci-0000:01:00.0-usb-0:{}:1.0"
NETWORK_PROFILES = (
    ("eth0-hpc", "eth0", "192.168.0.3/24"),  # HPC control/iot board at 192.168.0.2
    ("eth1-mcp", USB_PORT_PATH.format(2), "192.168.1.2/24"),  # eth1: MCP6 / MCPLA network
    ("eth2-bms", USB_PORT_PATH.format(3), "192.168.2.253/24"),  # eth2: BMS network
)
MCP_NETWORK_PROFILE = "eth1-mcp"
LEGACY_NETWORK_PROFILES = {"br0", "br0-port1", "br0-port2", "br0-static", "eth2-hpc"}
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


LOG_FILE = Path("/var/log/hpc-stock-installer.log")
# os-release style KEY=value record of what is installed: the golden image
# writes HPC_GOLDEN, provisioning writes HPC_SETUP*, the app install HPC_APP*.
RELEASE_INFO_FILE = Path("/etc/hpc-release")

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
                # The app creates settings.txt in its working directory (bin/);
                # it is this unit's configuration, so never replace or delete it.
                "--exclude=/settings.txt",
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

    # hmi.service grants the app's capabilities (AmbientCapabilities). Exec of
    # a binary with file capabilities clears the ambient set, so remove any
    # left by earlier installers (rsync keeps an unchanged binary as it is).
    # setcap -r fails on a binary that has none; that's fine.
    run([command_path("setcap"), "-r", str(app_dir / "HPC_LinuxGUI")], check=False)

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


def nmcli_lines(*args: str) -> list[str]:
    result = subprocess.run(
        [command_path("nmcli"), *args], check=True, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line]


def configure_network_profiles() -> None:
    """Create one static profile per port; HPC_LinuxGUI only sets their addresses.

    Names and addresses follow HPC_Firmware's
    LinuxHMI/HPC_LinuxGUI/include/HPC_LinuxGUI/system/network_config_nmcli.h.
    """
    nmcli = command_path("nmcli")
    run([nmcli, "connection", "reload"])

    # Profiles from earlier installers (eth2-hpc) and app versions (the br0 bridge).
    existing = nmcli_lines("-g", "NAME,UUID", "connection", "show")
    bridges = {"br0"}
    for line in existing:
        name, _, uuid = line.rpartition(":")
        if name == "br0":
            bridges.add(uuid)
    legacy = []
    for line in existing:
        name, _, uuid = line.rpartition(":")
        master = nmcli_lines("-g", "connection.master", "connection", "show", uuid)
        if name in LEGACY_NETWORK_PROFILES or (master and master[0] in bridges):
            legacy.append(uuid)
    for uuid in legacy:
        run([nmcli, "connection", "delete", uuid])

    names = {line.rpartition(":")[0] for line in nmcli_lines("-g", "NAME,UUID", "connection", "show")}
    for name, port, cidr in NETWORK_PROFILES:
        by_path = port.startswith("platform-")
        settings = [
            "connection.interface-name", "" if by_path else port,
            "match.path", port if by_path else "",
            "connection.autoconnect", "yes",
            # Wins over any other profile for the port, e.g. "Wired connection 1".
            "connection.autoconnect-priority", "100",
            "ipv4.method", "manual",
            "ipv4.gateway", "",
            "ipv4.dns", "",
            "ipv4.ignore-auto-dns", "yes",
            "ipv4.never-default", "yes",
            "ipv6.method", "disabled",
        ]
        if name not in names:
            run([nmcli, "connection", "add", "type", "ethernet", "con-name", name,
                 *settings, "ipv4.addresses", cidr])
        elif name == MCP_NETWORK_PROFILE:
            # The app has set this unit's unit-number address; keep it.
            run([nmcli, "connection", "modify", name, *settings])
        else:
            run([nmcli, "connection", "modify", name, *settings, "ipv4.addresses", cidr])


def install_system_file(name: str, destination: Path) -> None:
    """Install a file from the kit's system/ directory (from the app release)."""
    source = bundle_directory() / "system" / name
    if not source.is_file():
        raise RuntimeError(f"Missing release file: {source}")
    shutil.copyfile(source, destination)
    os.chown(destination, 0, 0)
    destination.chmod(0o644)


def configure_network_access() -> None:
    # Lets nwhs (the app) change NetworkManager profiles without sudo; polkitd
    # picks up new rules without a restart. Shipped with the app release
    # (HPC_Firmware LinuxHMI/HPC_LinuxGUI/scripts/hmi-networkmanager.rules).
    rules_directory = Path("/etc/polkit-1/rules.d")
    if not rules_directory.is_dir():
        raise RuntimeError(f"polkitd is not installed (no {rules_directory})")
    install_system_file(
        "hmi-networkmanager.rules", rules_directory / "50-hpc-hmi-networkmanager.rules"
    )


def configure_usb_update() -> None:
    """Install HMI releases from USB drives; see hpc-usb-update.py."""
    updater = Path("/usr/local/sbin/hpc-usb-update")
    source = bundle_directory() / "hpc-usb-update.py"
    if not source.is_file():
        raise RuntimeError(f"Missing updater: {source}")
    shutil.copyfile(source, updater)
    os.chown(updater, 0, 0)
    updater.chmod(0o755)

    units = {
        "hpc-usb-update@.service": f"""[Unit]
Description=Check USB drive %I for an HMI release

[Service]
Type=oneshot
ExecStart={updater} --scan /dev/%I
""",
        # Started by the panel creating /run/hpc-update/install.
        "hpc-usb-update-apply.service": f"""[Unit]
Description=Install the HMI release copied from a USB drive

[Service]
Type=oneshot
ExecStart={updater} --apply
TimeoutStartSec=300
""",
        "hpc-usb-update-apply.path": """[Unit]
Description=Watch for the panel asking to install an HMI release

[Path]
PathExists=/run/hpc-update/install

[Install]
WantedBy=multi-user.target
""",
        "hpc-usb-update-boot.service": f"""[Unit]
Description=Recover from an interrupted HMI update
After=local-fs.target
Before=hmi.service hpc-usb-update-apply.path

[Service]
Type=oneshot
ExecStart={updater} --boot

[Install]
WantedBy=multi-user.target
""",
    }
    for name, text in units.items():
        Path("/etc/systemd/system", name).write_text(text, encoding="utf-8")

    # vfat only: the app's log drive code mounts nothing else.
    Path("/etc/udev/rules.d/99-hpc-usb-update.rules").write_text(
        'ACTION=="add", SUBSYSTEM=="block", ENV{ID_BUS}=="usb", ENV{ID_FS_TYPE}=="vfat", '
        'TAG+="systemd", ENV{SYSTEMD_WANTS}+="hpc-usb-update@%k.service"\n',
        encoding="utf-8",
    )

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "hpc-usb-update-apply.path", "hpc-usb-update-boot.service"])
    run(["udevadm", "control", "--reload-rules"])


def configure_sudo_access() -> None:
    # Membership in sudo grants normal administrative access using the nwhs
    # password. The app changes the network through polkit, so nothing is
    # passwordless any more.
    # Remove the filename used by earlier revisions of this installer.
    Path(f"/etc/sudoers.d/{APP_USER}-networkmanager").unlink(missing_ok=True)

    sudoers = Path(f"/etc/sudoers.d/{APP_USER}-hpc")
    sudoers.write_text(f"{APP_USER} ALL=(ALL:ALL) ALL\n", encoding="utf-8")
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

def detect_legacy_users() -> list[str]:
    """Every regular login account other than APP_USER (stock, Imager-made, or ad hoc)."""
    return sorted(
        user.pw_name
        for user in pwd.getpwall()
        if user.pw_uid in REGULAR_UID_RANGE and user.pw_name != APP_USER
    )


def configure_legacy_user_cleanup() -> None:
    """Lock old login users now and remove them safely during the reboot."""
    legacy_users = detect_legacy_users()
    for user_name in legacy_users:
        run(["usermod", "--lock", user_name])
    if legacy_users:
        logging.info("Legacy users to remove on reboot: %s", ", ".join(legacy_users))

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
    # userdel leaves sudo rules behind, e.g. Raspberry Pi OS's 010_pi-nopasswd
    for rule in /etc/sudoers.d/*; do
        [ -f "$rule" ] || continue
        if awk -v u="$user_name" '$1 == u { found = 1 } END { exit !found }' "$rule"; then
            rm -f "$rule"
        fi
    done
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

    # The app's own unit, shipped with its release (HPC_Firmware
    # LinuxHMI/HPC_LinuxGUI/scripts/hmi.service).
    install_system_file("hmi.service", Path("/etc/systemd/system/hmi.service"))

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


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def update_release_info(values: dict[str, str]) -> None:
    """Set these keys in /etc/hpc-release, keeping every other line."""
    # Values must be shell-sourceable without quotes.
    values = {key: re.sub(r"[^A-Za-z0-9._:+-]", "_", value) for key, value in values.items()}
    lines = []
    if RELEASE_INFO_FILE.is_file():
        lines = RELEASE_INFO_FILE.read_text(encoding="utf-8").splitlines()

    remaining = dict(values)
    updated = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    updated.extend(f"{key}={value}" for key, value in remaining.items())

    temporary = RELEASE_INFO_FILE.with_name(f".{RELEASE_INFO_FILE.name}.tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    temporary.chmod(0o644)
    os.replace(temporary, RELEASE_INFO_FILE)
    logging.info("Recorded in %s: %s", RELEASE_INFO_FILE, ", ".join(f"{k}={v}" for k, v in values.items()))


def read_setup_version() -> str:
    """The kit's VERSION file as "setup-vX.Y.Z", or "unknown" for an older kit."""
    version_file = bundle_directory() / "VERSION"
    if version_file.is_file():
        for line in version_file.read_text(encoding="utf-8").splitlines():
            if re.fullmatch(r"\d+\.\d+\.\d+", line.strip()):
                return f"setup-v{line.strip()}"
    return "unknown"


def record_app_release(app_dir: Path) -> None:
    """Record the installed app's version and source commit from its release manifest."""
    manifest_file = app_dir / "release-manifest.json"
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    update_release_info({
        "HPC_APP": str(manifest.get("release_version") or "unknown"),
        "HPC_APP_COMMIT": str(manifest.get("source_commit") or "unknown"),
        "HPC_APP_DATE": utc_timestamp(),
    })


def record_setup_release() -> None:
    values = {"HPC_SETUP": read_setup_version(), "HPC_SETUP_DATE": utc_timestamp()}
    # Golden images from before /etc/hpc-release existed (2026-10-22) have no HPC_GOLDEN.
    existing = RELEASE_INFO_FILE.read_text(encoding="utf-8") if RELEASE_INFO_FILE.is_file() else ""
    if not re.search(r"^HPC_GOLDEN=", existing, re.MULTILINE):
        values["HPC_GOLDEN"] = "unknown"
    update_release_info(values)


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

    ensure_user()
    install_application(source_dir, app_dir)
    record_app_release(app_dir)
    configure_hostname()
    configure_network_profiles()
    configure_network_access()
    configure_sudo_access()
    configure_touchscreen_udev()
    configure_boot(app_dir)
    configure_usb_update()
    configure_legacy_user_cleanup()
    record_setup_release()

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
    parser = argparse.ArgumentParser(
        description="Provision a stock EDATEC HMI"
    )

    # Internal arguments used when relaunching from the desktop or through sudo.
    parser.add_argument(
        "--terminal",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--as-root",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    if os.geteuid() != 0:
        if not sys.stdout.isatty() and not args.terminal:
            if open_own_terminal():
                return 0

        return elevate_without_prompt()

    configure_logging()

    try:
        provision()
    except Exception as exc:
        logging.error("Provisioning failed: %s", exc)
        logging.error("%s", traceback.format_exc())
        show_notification("HPC installer failed", str(exc), "critical")
        time.sleep(20)
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit_status = main()
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        exit_status = 1

    raise SystemExit(exit_status)
