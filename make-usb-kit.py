#!/usr/bin/env python3
"""Assemble an offline provisioning kit (USB contents) for the HPC HMI.

Runs on the maintainer's computer. Combines this repo's setup payload
(stock-hmi.py, hpc-usb-update.py, VERSION, debs/) with one HMI release from a
local hpc-releases checkout, verified against the release manifest.
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO_DIRECTORY = Path(__file__).resolve().parent
PAYLOAD_DIRECTORY = REPO_DIRECTORY / "BOOKWORM"
DEFAULT_RELEASES = REPO_DIRECTORY.parent / "hpc-releases"
RELEASE_NAME_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(-RC\d+)?$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Everything this script writes at the top level of the kit; --replace removes
# only these, so unrelated files on the stick are left alone. network/ is from
# older kits and is no longer written.
KIT_ENTRIES = ("stock-hmi.py", "hpc-usb-update.py", "VERSION", "bin", "system", "debs", "network",
               "KIT.txt", "SHA256SUMS")
# Release manifest components installed outside the app directory, and their
# names in the kit's system/ directory (stock-hmi.py installs them from there).
SYSTEM_FILES = {
    "hmi_service": "hmi.service",
    "hmi_polkit_rules": "hmi-networkmanager.rules",
}


def calculate_sha256(filename: Path) -> str:
    digest = hashlib.sha256()
    with filename.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_setup_version() -> str:
    """Return this repo's setup version from VERSION, e.g. "setup-v1.0.0"."""
    version_file = REPO_DIRECTORY / "VERSION"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if VERSION_PATTERN.match(line):
            return f"setup-v{line}"
    raise RuntimeError(f"{version_file} must contain a MAJOR.MINOR.PATCH line")


def resolve_release(releases: Path, name: str | None) -> Path:
    """Return versions/<name>/, taking the name from CURRENT when not given."""
    if name is None:
        current_file = releases / "CURRENT"
        if not current_file.is_file():
            raise RuntimeError(f"Release repository has no CURRENT file: {current_file}")
        name = current_file.read_text(encoding="utf-8").strip()

    if not RELEASE_NAME_PATTERN.match(name):
        raise RuntimeError(f"Invalid release name: {name!r}")

    release_directory = releases / "versions" / name
    if not release_directory.is_dir():
        raise RuntimeError(f"Release does not exist: {release_directory}")
    return release_directory


def load_component(release_directory: Path, manifest: dict, component: str) -> Path:
    """The release file for a manifest component, verified against its SHA-256."""
    try:
        release_filename = manifest["components"][component]["file"]
        expected_sha256 = manifest["components"][component]["sha256"].lower()
    except (KeyError, TypeError, AttributeError) as error:
        hint = ""
        if component in SYSTEM_FILES:
            hint = " (v2.0.8 and earlier don't ship it; use a newer release)"
        raise RuntimeError(
            f"The release manifest does not contain a valid {component} component{hint}"
        ) from error

    # Prevent a manifest filename from escaping the release directory.
    if Path(release_filename).name != release_filename:
        raise RuntimeError(f"Invalid {component} filename in manifest: {release_filename}")

    release_file = release_directory / release_filename
    if not release_file.is_file():
        raise RuntimeError(f"Release {component} file does not exist: {release_file}")

    actual_sha256 = calculate_sha256(release_file)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Release {component} SHA-256 verification failed:\n"
            f"  Expected: {expected_sha256}\n"
            f"  Actual:   {actual_sha256}"
        )
    return release_file


def load_release(release_directory: Path) -> tuple[dict, dict[str, Path]]:
    manifest_file = release_directory / "manifest.json"
    if not manifest_file.is_file():
        raise RuntimeError(f"Release does not contain a manifest: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    files = {component: load_component(release_directory, manifest, component)
             for component in ("hmi", *SYSTEM_FILES)}
    if not (release_directory / "assets").is_dir():
        raise RuntimeError(f"HMI release assets do not exist: {release_directory / 'assets'}")
    return manifest, files


def git_description(directory: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), "describe", "--always", "--dirty", "--tags"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown (not a git checkout)"


def prepare_output(output: Path, replace: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    present = [entry for entry in KIT_ENTRIES if (output / entry).exists()]
    if present and not replace:
        raise RuntimeError(
            f"{output} already holds a kit ({', '.join(present)}); pass --replace to overwrite it"
        )
    for entry in present:
        path = output / entry
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def copy_tree(source: Path, destination: Path) -> None:
    # copyfile only: FAT sticks can't hold Unix permissions or ownership.
    shutil.copytree(source, destination, copy_function=shutil.copyfile)


def write_checksums(output: Path) -> None:
    lines = []
    for path in sorted(output.rglob("*")):
        relative = path.relative_to(output)
        if path.is_file() and relative.parts[0] in KIT_ENTRIES and relative.name != "SHA256SUMS":
            lines.append(f"{calculate_sha256(path)}  ./{relative.as_posix()}\n")
    (output / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def build_kit(output: Path, releases: Path, release_name: str | None, replace: bool) -> None:
    setup_version = read_setup_version()
    release_directory = resolve_release(releases, release_name)
    manifest, release_files = load_release(release_directory)
    release_binary = release_files["hmi"]
    for required in (REPO_DIRECTORY / "stock-hmi.py", REPO_DIRECTORY / "hpc-usb-update.py",
                     PAYLOAD_DIRECTORY / "debs"):
        if not required.exists():
            raise RuntimeError(f"Missing setup payload: {required}")

    prepare_output(output, replace)

    shutil.copyfile(REPO_DIRECTORY / "stock-hmi.py", output / "stock-hmi.py")
    shutil.copyfile(REPO_DIRECTORY / "hpc-usb-update.py", output / "hpc-usb-update.py")
    shutil.copyfile(REPO_DIRECTORY / "VERSION", output / "VERSION")
    copy_tree(PAYLOAD_DIRECTORY / "debs", output / "debs")

    bin_directory = output / "bin"
    copy_tree(release_directory / "assets", bin_directory / "assets")
    shutil.copyfile(release_binary, bin_directory / "HPC_LinuxGUI")
    shutil.copyfile(release_directory / "manifest.json", bin_directory / "release-manifest.json")

    system_directory = output / "system"
    system_directory.mkdir()
    for component, kit_name in SYSTEM_FILES.items():
        shutil.copyfile(release_files[component], system_directory / kit_name)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (output / "KIT.txt").write_text(
        f"built:     {built}\n"
        f"setup:     {setup_version}\n"
        f"app:       {manifest.get('release_version', release_directory.name)}"
        f" ({release_binary.name})\n"
        f"stock_hmi: {git_description(REPO_DIRECTORY)}\n"
        f"releases:  {git_description(releases)}\n",
        encoding="utf-8",
    )
    write_checksums(output)

    print((output / "KIT.txt").read_text(encoding="utf-8"), end="")
    print(f"Kit written to {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble the HPC HMI provisioning USB")
    parser.add_argument("output", type=Path, help="kit destination, e.g. the USB mount point")
    parser.add_argument(
        "--releases",
        type=Path,
        default=DEFAULT_RELEASES,
        help=f"local hpc-releases checkout (default: {DEFAULT_RELEASES})",
    )
    parser.add_argument("--release", help="release name, e.g. v2.0.8 (default: the one in CURRENT)")
    parser.add_argument("--replace", action="store_true", help="overwrite a kit already at OUTPUT")
    args = parser.parse_args()

    try:
        build_kit(args.output.resolve(), args.releases.resolve(), args.release, args.replace)
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
