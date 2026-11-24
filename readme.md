## Stock HMI Provisioner for the EDATEC ED-HMI2220-070C
- IMGAGE moved to HPC_Firmware/hmi_provisioning/images/OS_img
- WIP in: HPC_Firmware/hmi_provisioning/
- provissional tool now mangaged in main repo
- Included image publicly available for OEM EDATEC support. 


## Overview

This package provisions a stock EDATEC ED-HMI2220-070C for use as an HPC HMI.
Load the package to a stock EDATEC OS installation, then run the provisioning
script. The script configures the operating system, user account, application,
and startup services.

## Package structure

```text
USB_ROOT/
├── bin
│   ├── assets
│   ├── HPC_LinuxGUI
│   └── settings.txt
├── debs
|    ├── iptables_1.8.11-2_arm64.deb
|    ├── libip6tc-dev_1.8.11-2_arm64.deb
|    ├── libpaho-mqtt-dev_1.3.14-2_arm64.deb
|    └── libx11-dev_2%3a1.8.12-1_arm64.deb
|
└── stock-hmi
```

The `bin` directory must contain the precompiled `HPC_LinuxGUI` executable, its
complete `assets` directory

The `debs` folder must contain required TRIXIE deb packages

## Usage

Run the provisioner by double clicking `stock-hmi.py`
the provissioning script will find the bin, and debs folders and install the package constituents. 



## Installation behavior

The provisioner copies the application files to:

```text
/home/<user>/hpc-hmi/bin/
```

It then creates a service that automatically starts:

```text
/home/<user>/hpc-hmi/bin/HPC_LinuxGUI
```
at the end of the installation, the HMI will reboot, and the HPC GUI will load. 
  
## Building usb provissionging media
run 
```
make-usb-kit.py <usb_target>
```

## Security

No passwords are stored in the provisioning script.  
catagorical image verification, and checksums stored in main repo.

## OS and glibc compatibility

`HPC_LinuxGUI` dynamically links against `libc6` (glibc), which is supplied by
the operating system:

| OS | glibc version | Application build |
| --- | --- | --- |
| Debian 13 (Trixie) | 2.38 | `TRIXIE/` |


