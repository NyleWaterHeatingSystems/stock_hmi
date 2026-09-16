# Stock HMI Provisioner for the EDATEC ED-HMI2220-070C

> **Work in progress:** This is currently an online installer. The HMI must have
> internet access so the provisioner can install required packages, including
> `libx11-dev` and `libpaho-mqtt-dev`.

## Overview

This package provisions a stock EDATEC ED-HMI2220-070C for use as an HPC HMI.
Download the package to a stock EDATEC OS installation, then run the provisioning
script. The script configures the operating system, user account, application,
and startup service.

## Package structure

```text
stock-hmi.py
bin/
├── HPC_LinuxGUI
├── assets/
└── settings.txt
```

The `bin` directory must contain the precompiled `HPC_LinuxGUI` executable, its
complete `assets` directory, and `settings.txt`.

## Usage

Run the provisioner from the directory containing `stock-hmi.py` and `bin/`:

```bash
sudo python3 stock-hmi.py
```

The current installer requires an internet connection to retrieve its package
dependencies.

## Installation behavior

The provisioner copies the application files to:

```text
/home/<user>/hpc-hmi/bin/
```

It then creates a service that automatically starts:

```text
/home/<user>/hpc-hmi/bin/HPC_LinuxGUI
```

The service assumes that the executable is named `HPC_LinuxGUI` and remains in
that location. If the name or installation path changes, the service definition
in `stock-hmi.py` must also be updated.

## Maintenance and rebuilding

- To update the HMI application, replace `HPC_LinuxGUI`, `assets/`, and
  `settings.txt` in `bin/` before running the provisioner.
- To change OS, user-account, or service configuration, edit `stock-hmi.py`.
- The application is installed from a precompiled binary; it is not compiled by
  the provisioner.

## Security

No passwords are stored in the provisioning script. Installation of the HMI
application is based on the supplied precompiled `HPC_LinuxGUI` binary and its
supporting files.

## OS and glibc compatibility

`HPC_LinuxGUI` dynamically links against `libc6` (glibc), which is supplied by
the operating system:

| OS | glibc version | Application build |
| --- | --- | --- |
| Debian 12 (Bookworm) | 2.36 | `BOOKWORM/` |
| Debian 13 (Trixie) | 2.38 | `TRIXIE/` |

A binary built on Trixie may require symbols introduced in glibc 2.38 and will
not run on the stock Bookworm image, which provides glibc 2.36. The loader will
typically report an error such as `GLIBC_2.38 not found`.

A binary built on Bookworm generally has the safer compatibility baseline and
will normally run on Trixie, although compatibility can still be affected by
other dynamically linked libraries.

Do not attempt to solve this by manually upgrading `libc6` on the stock image.
A partial glibc upgrade can make the operating system unusable. Instead, use the
`HPC_LinuxGUI` build that matches the target OS, or build on the oldest OS that
must be supported.

EDATEC support for Debian 13 (Trixie) is still incomplete for some HMI hardware
variants. Display, touchscreen, and other device-specific drivers may behave
differently between models and OS releases.

## Building a standalone provisioner

The Python script can be packaged as a single executable with PyInstaller:

```bash
python3 -m PyInstaller --onefile --name stock-hmi stock-hmi.py
```

The resulting executable will be placed at:

```text
dist/stock-hmi
```

PyInstaller packages only the provisioning script. The `bin/` directory and its
contents must still be distributed alongside the executable unless they are
explicitly added to the PyInstaller bundle and the script is updated to locate
bundled resources.

> **Note:** The PyInstaller build has not yet been tested.

## EDATEC reference

EDATEC documents its firmware-package installation process here:

<https://edatec.cn/docs/hmi2220-101c/um/6-installing-os/#_6-3-installing-firmware-package>

The referenced installer command is:

```bash
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-101c
```

Trixie compatable drivers  
<https://edatec.cn/docs/an/an44-use-7-inch-and-10.1-inch-hmi-on-standard-rpi-os/>
