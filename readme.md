# Stock HMI Provisioner for the EDATEC ED-HMI2220-070C

> **Work in progress:** This is now an offline installer, with the option 
>  to update the HPC_HMI software (online) From:
>  https://github.com/NyleWaterHeatingSystems/hpc-releases


## Overview

This package provisions a stock EDATEC ED-HMI2220-070C for use as an HPC HMI.
Download the package to a stock EDATEC OS installation, then run the provisioning
script. The script configures the operating system, user account, application,
and startup service.

## Package structure

```text
OS_Version/
├── bin
│   ├── assets
│   ├── HPC_LinuxGUI
│   └── settings.txt
├── debs
│   ├── iptables_1.8.9-2_arm64.deb
│   ├── libpaho-mqtt1.3_1.3.12-1_arm64.deb
│   └── libx11-dev_2%3a1.8.4-2+deb12u2_arm64.deb
└── stock-hmi.py

```

The `bin` directory must contain the precompiled `HPC_LinuxGUI` executable, its
complete `assets` directory, and `settings.txt`.

The `debs` folder must contain both the the HMI program dependencies, AND
the additional software packages you want to install. 
```bash
$ stock-hmi --update
```
Will only update the HPC HMI software, and WILL NOT try to update the OS_version
matched application dependencies or additional software packages.

## Usage

Run the provisioner from the directory containing `stock-hmi.py`, `bin/` and `debs`:

```bash
$./stock-hmi.py
```
The installer may also operated from a USB stick, by running the precompiled
`stock-hmi` application provided it is accompanied by the contents of `bin` and `debs`

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

- To update the HMI application, run $`./stock-hmi.py --update`  
- To change OS, user-account, or service configuration, edit `stock-hmi.py`.
- To add additional packages, include the deb files in the debs directoy.
- The application is installed from a precompiled binary; it is not compiled by
  stock-hmi.py.

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

For now, compiling the HPC_LinuxGUI on the OLD Stable ( BOOKWORM )
allows the HMI binary HPC_LinuxGUI to run on both the Old Stable, and updated
Current Stable ( TRIXIE ) releases. This will be simpler than maintaining 
two versions.  

EDATEC support for Debian 13 ( Trixie ) is still incomplete for some HMI hardware
variants. Display, touchscreen, and other device-specific drivers may behave
differently between models and OS releases.

## Building a compiled binary of stock-hmi.py

The Python script can be packaged as a single executable with PyInstaller:

```bash
python3 -m PyInstaller --onefile --name stock-hmi stock-hmi.py
```

The resulting executable will be placed at:

```text
dist/stock-hmi
```
Copy the compiled stock-hmi binary to the root project directory. 

PyInstaller packages only the provisioning script. The `bin/`, `debs` directories and 
thier contents must still be distributed alongside the executable as
bundled resources.


## EDATEC reference

EDATEC documents its firmware-package installation process here:

<https://edatec.cn/docs/hmi2220-101c/um/6-installing-os/#_6-3-installing-firmware-package>

The referenced installer command is:

```bash
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-070c
```

Trixie compatable drivers  
<https://edatec.cn/docs/an/an44-use-7-inch-and-10.1-inch-hmi-on-standard-rpi-os/>
