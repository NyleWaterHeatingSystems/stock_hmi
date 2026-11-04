# Stock HMI Provisioner for the EDATEC ED-HMI2220-070C

Provisions an EDATEC ED-HMI2220-070C, flashed with the golden image, as an HPC
HMI. Only maintainers provision HMIs; technicians only update provisioned ones.
Both work fully offline with a laptop, an Ethernet cable and the provisioning
USB. Step-by-step instructions, with expected output for every
check, are in [HOWTO_golden_image.md](HOWTO_golden_image.md).

## Current state (2026-10-23)

- The golden image `hpc-golden-2026-10-22.img.xz` (Bookworm Lite, EDATEC
  kernel 6.6.31, login `pi` / `raspberry`) has been built, flashed and
  provisioned on real hardware with app v2.0.8.
- It's stored in Google Drive for now:
  [folder](https://drive.google.com/drive/folders/1tibp_miz9kWSzZj1l7MBG5oEfH0VU8Kn?usp=drive_link),
  [image](https://drive.google.com/file/d/1WYvcbQXtD-RB6T1y32ddFpm1zrGR32Wt/view?usp=drive_link).
  This location may move. TODO: create a formal storage place for images.
- Remaining work is listed under "Open items" at the end of the HOWTO. The most
  important: no released app keeps eth2 at `192.168.0.4` yet (v2.0.8 moves it to
  `192.168.0.1`), and the update path has not been tested on hardware.
- This repo works together with `hpc-releases` (app releases, checked out next
  to this repo) and `HPC_Firmware` (app source).

## Repository layout

```text
stock_hmi/
├── stock-hmi.py          # the provisioner; runs on the HMI as root
├── make-usb-kit.py       # builds the provisioning USB on the maintainer's PC
├── hpc-gateway-ports.sh  # exposes the HPC's variables to hpc-gateway; also runs alone
├── VERSION               # setup version (semver), tagged setup-vX.Y.Z
├── BOOKWORM/             # setup payload for Debian 12 (Bookworm)
│   ├── debs/             # offline .deb dependencies
│   └── network/          # eth2-hpc.nmconnection: golden image only (HOWTO 1.5)
├── golden_image/         # EDATEC install scripts used to build the golden image
└── HOWTO_golden_image.md
```

The HMI application is **not** stored here. Releases live in the sibling
[`hpc-releases`](https://github.com/NyleWaterHeatingSystems/hpc-releases)
repository, and `make-usb-kit.py` copies one in when it builds a kit.

## Building the provisioning USB

```bash
./make-usb-kit.py /run/media/$USER/<USB>              # release named in hpc-releases/CURRENT
./make-usb-kit.py /run/media/$USER/<USB> --release vX.Y.Z
./make-usb-kit.py /run/media/$USER/<USB> --replace    # overwrite an existing kit
```

By default it reads `../hpc-releases`; use `--releases PATH` for another
checkout. It verifies the HMI binary, `hmi.service` and the polkit rule against
the release manifest, then writes. It refuses a release without `hmi_service`
and `hmi_polkit_rules` components (v2.0.8 and earlier):

```text
USB/
├── stock-hmi.py
├── hpc-gateway-ports.sh
├── VERSION
├── bin/                  # HPC_LinuxGUI, assets/, release-manifest.json
├── system/               # hmi.service, hmi-networkmanager.rules (from the release)
├── debs/
├── KIT.txt               # setup version, release, stock_hmi commit and build time
└── SHA256SUMS            # check on the HMI with: sha256sum -c SHA256SUMS
```

## Usage

On the HMI, from the mounted USB:

```bash
sudo python3 ./stock-hmi.py
```

It installs the debs, creates the `nwhs` user, copies `bin/` to
`/home/nwhs/hpc-hmi/bin/`, configures the hostname, HPC port, sudo, touchscreen
and startup services, removes every other login user on the next boot, and
reboots. Re-running it with a newer kit is the update path.

The startup service runs `/home/nwhs/hpc-hmi/bin/HPC_LinuxGUI`. If that name or
path changes, update the service definition in `stock-hmi.py`.

## hpc-gateway access

`hpc-gateway` reaches all three variable tables at the HMI's MCP address,
`192.168.1.(unit number + 1)`, from a machine on the MCP network:

| Variables | `hmi_port` | Reaches |
| --- | --- | --- |
| HMI | 2324 | the HMI's own proxy (no setup needed) |
| HPC IoT board | 5324 | `192.168.0.2:2324` |
| HPC control board | 5325 | `192.168.0.2:2325` |

New provisioning sets this up. To patch a unit that's already provisioned, with
no reboot, run this from a laptop on the HPC link or the MCP network, using the
HMI's address on that network:

```bash
scp hpc-gateway-ports.sh nwhs@<HMI>:
ssh -t nwhs@<HMI> sudo sh hpc-gateway-ports.sh install
```

`status` shows the state, and `remove` undoes it. The setting lasts across power
cycles and app updates. It also supports apps up to v2.0.9, which use `br0`.
Tested in network namespaces only. TODO: test on hardware.

Run one gateway per table. Each needs its own conf file and its own
`modbus_bind` and `http_bind`, because a conf file holds one table's point rows.
For unit 1, the control board:

```text
hmi_addr = 192.168.1.2
hmi_port = 5325
modbus_bind = 0.0.0.0:8503
http_bind = 0.0.0.0:8083
```

- Each port serves one client: the proxy replies to whoever wrote last. Don't
  point a second gateway or `hpc_console` at a port that's in use.
- The gateway must have an address on `192.168.1.0/24`. The ports don't answer
  from other networks, including the BMS network.
- These ports give full proxy access, not read-only access: the firmware doesn't
  enforce authentication, so anything on the MCP network can also write
  variables or reboot the boards through them. The gateway itself only reads.

## Maintenance

- New HMI release: publish it to `hpc-releases`, then rebuild the kit.
- New or updated packages: add the .deb files to `BOOKWORM/debs/`.
- OS, user, network or service configuration: edit `stock-hmi.py` or the files
  in `BOOKWORM/`.

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

PyInstaller packages only the provisioning script. The `bin/`, `debs/` and
`network/` directories must still sit next to the executable. Build it on arm64
(on an HMI), since PyInstaller does not cross-compile.

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



## EDATEC reference

EDATEC documents its firmware-package installation process here:

<https://edatec.cn/docs/hmi2220-101c/um/6-installing-os/#_6-3-installing-firmware-package>

The referenced installer command is:

```bash
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-070c
```

Trixie compatable drivers  
<https://edatec.cn/docs/an/an44-use-7-inch-and-10.1-inch-hmi-on-standard-rpi-os/>
