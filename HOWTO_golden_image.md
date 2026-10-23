# HPC HMI: Golden Image, Provisioning, and Updates

This guide covers the EDATEC **ED-HMI2220-070C** used as the HPC HMI. The unit
is a Raspberry Pi **Compute Module 4** with a 29.1 GiB eMMC and a 7" DSI touch
panel. The guide explains how the golden image was built, how to turn a flashed
HMI into a working HPC HMI, and how to update one. Every check shows the command
to run and the output seen on real hardware, so you can tell whether a step
worked.

## How the pieces fit together

The HMI's software is built in three layers. Each layer changes at its own pace
and has its own version:

| Layer | What it is | Where it lives | Changes |
| --- | --- | --- | --- |
| **Golden image** | Raspberry Pi OS Bookworm Lite plus EDATEC's kernel and drivers, with a `pi` user and SSH on. No HPC software. | Google Drive (see [Where the images are stored](#where-the-images-are-stored)) | Rarely |
| **Setup** | `stock-hmi.py` and its payload (`BOOKWORM/debs/`, `BOOKWORM/network/`). Turns a golden image into an HPC HMI. | This repo | Sometimes |
| **App** | `HPC_LinuxGUI` and its assets, built from `HPC_Firmware`. | The `hpc-releases` repo | Often |

`make-usb-kit.py` combines the setup payload with one app release into a
**provisioning USB**. A technician flashes the golden image, then runs the
provisioner from that USB. Neither step needs internet.

The golden image is also the developers' clean starting point. Re-flash it to
get a unit back to a known state before trying a new setup script or
configuration.

## Who does what

| Section | Who | Network |
| --- | --- | --- |
| [0. Background and laptop setup](#0-background-and-laptop-setup) | Anyone, once per laptop | Internet to install tools |
| [1. Creating the golden image](#1-creating-the-golden-image) | Maintainer, at the shop | Internet needed once (EDATEC drivers) |
| [2. Provisioning an HMI](#2-provisioning-an-hmi-from-the-golden-image) | Technician, in the field | **Offline**: laptop, Ethernet cable and USB |
| [3. Updating the HMI software](#3-updating-the-hmi-software) | Maintainer, then technician | Internet for the maintainer only |

Steps that have not yet been run on real hardware are marked **TODO**. The full
list of open items is in [Open items](#open-items) at the end.

---

## 0. Background and laptop setup

### Hardware facts

- `cat /proc/device-tree/model` prints `Raspberry Pi Compute Module 4 Rev 1.1`.
- The OS lives on **eMMC**: flash memory soldered to the board. There is no SD
  card to remove. You can tell it's eMMC because `lsblk` lists `mmcblk0boot0`
  and `mmcblk0boot1`.
- To write the eMMC from a PC, the CM4 is put into **USB-boot mode**. A tool
  called `rpiboot` then makes the eMMC appear on the PC as an ordinary USB disk.
  This HMI has **no boot switch or jumper**. If its Micro USB port is connected
  to a PC when it powers on, it enters USB-boot mode by itself. In that mode its
  screen stays black.
- The EDATEC display and touch only work with **EDATEC's 6.6.31 kernel**. The
  stock Raspberry Pi OS kernel (6.12.x) boots, but the screen stays black.

### Install the laptop tools

These commands are for Arch Linux. On another distribution, install the same
programs with its package manager.

```bash
sudo pacman -S rpi-imager dnsmasq
yay -S rpiusbboot            # AUR package; builds github.com/raspberrypi/usbboot and installs `rpiboot`
yay -S pishrink-git          # only needed to capture a new golden image (1.6)
```

### Download the rpiboot loader for the CM4

`rpiboot` sends the CM4 a small "loader" program that exposes the eMMC over USB.
The loader in the current `usbboot` release (`mass-storage-gadget64`) starts the
CM4, but **the eMMC never appears** on this HMI, and the current `msd` folder has
no CM4 files. Use the older loader from release `20221215-105525` instead:

```bash
mkdir -p ~/rpiboot-msd-cm4 && cd ~/rpiboot-msd-cm4
base=https://raw.githubusercontent.com/raspberrypi/usbboot/20221215-105525
curl -fsSLO $base/msd/bootcode.bin
curl -fsSLO $base/msd/start.elf
curl -fsSLO $base/msd/start4.elf
# msd/bootcode4.bin is a git symlink, so fetch the real file from the repo root:
curl -fsSLo bootcode4.bin $base/bootcode4.bin
ls -la
```

**Check:** `bootcode4.bin` must be 106008 bytes. If it is 16 bytes, you
downloaded the symlink instead of the file; repeat the last `curl`.

Technicians have no internet, so copy this folder onto their USB as well.

### Connect the laptop to the HMI with a cable

The laptop talks to the HMI over a direct Ethernet cable. No router, Wi-Fi or
internet is needed.

#### Normal method: the HPC port (eth2) at 192.168.0.4

Every HMI flashed with the golden image, and every provisioned HMI, has a fixed
address on its **HPC controller port, eth2: `192.168.0.4/24`**. (The HPC
controller itself is `192.168.0.2`.) To connect:

1. Plug the laptop into the HMI's eth2 socket. In the field, unplug the
   controller's cable from that socket first, or put a small switch between
   them.
2. Give the laptop the address `192.168.0.100`. On a Linux laptop with
   NetworkManager (`eno1` is the laptop's Ethernet port; list yours with
   `ip -br link`):
   ```bash
   nmcli con add type ethernet ifname eno1 con-name hmi-eth2 \
     ipv4.method manual ipv4.addresses 192.168.0.100/24 ipv6.method link-local
   nmcli con up hmi-eth2
   ```
3. Log in:
   ```bash
   ssh pi@192.168.0.4          # a freshly flashed golden image
   ssh nwhs@192.168.0.4        # a provisioned HMI
   ```

Never give the laptop `.4` (the HMI) or `.2` (the controller).

**If your laptop is also on a `192.168.0.x` Wi-Fi network** (common for
development PCs; the first build's PC had its router at `.1`), the laptop
already sends all of `192.168.0.x` to Wi-Fi. Send only the HMI's address down
the cable with a host route, and Wi-Fi keeps working:

```bash
nmcli con modify hmi-eth2 ipv4.addresses 192.168.0.100/32 ipv4.routes "192.168.0.4/32"
nmcli con up hmi-eth2
```

This is also why the HMI's eth2 moved from `.1` to `.4`: a route for `.1` would
capture the router as well.

Which socket is eth2? It's the USB network chip on USB path `usb-0:3`; see the
port table in [1.5](#fixed-address-on-the-hpc-port-eth2).
TODO: record which labelled socket on the case that is.

#### Fallback: the laptop as a DHCP server

Use this for a stock Raspberry Pi OS image (which has no fixed address) or when
you can't use eth2. A stock image asks for an address by DHCP on every port, and
on a direct cable nothing answers unless the laptop does. A NetworkManager
**shared** profile makes the laptop a DHCP server. It doesn't need internet, but
if the laptop has internet, the HMI gets it too, which section 1.3 relies on.

```bash
sudo ip addr flush dev eno1          # only if you added an address to eno1 by hand earlier
nmcli con add type ethernet ifname eno1 con-name hmi-direct \
  ipv4.method shared ipv4.addresses 192.168.1.200/24 \
  ipv6.method link-local
nmcli con up hmi-direct
```

After the HMI boots, find the address it was given and log in:

```bash
cat /var/lib/NetworkManager/dnsmasq-eno1.leases   # look for "raspberrypi" or "hpc"
ssh pi@192.168.1.<x>
```

If the HMI has no IPv4 address at all, use IPv6 link-local addresses, which
every device creates for itself:

```bash
ping -6 -c3 ff02::1%eno1                  # every device on the cable replies with its fe80:: address
ssh pi@fe80::xxxx:xxxx:xxxx:xxxx%eno1
```

Don't rely on `.local` names such as `raspberrypi.local`. They only work if the
laptop runs mDNS (avahi and `nss-mdns`).

On Windows, "Internet Connection Sharing" does the same job, and the HMI gets a
`192.168.137.x` address. TODO: not yet tried.

### Procedure: expose the eMMC on the laptop

Sections 1.1, 1.6 and 1.7 all start by making the HMI's eMMC appear on the
laptop as a USB disk:

1. Unplug other USB drives from the laptop. A 29.1G thumbdrive looks almost
   identical to the eMMC, and writing to the wrong disk destroys its contents.
2. Connect a **data-capable** Micro USB to USB-A cable from the HMI's Micro USB
   port to the laptop. (Some cables carry power only.) Keep the HMI's normal
   power on its DC 2-pin Phoenix terminal.
3. Start the loader **first** and leave it waiting:
   ```bash
   sudo rpiboot -v -d ~/rpiboot-msd-cm4
   ```
4. Power-cycle the HMI at the DC terminal. It only checks for USB boot at
   power-on.
5. `rpiboot` sends the loader and exits by itself. That's normal: the eMMC
   stays exposed until the HMI is powered off.
6. After about 10 s, run `lsblk -o NAME,SIZE,TRAN,MODEL,SERIAL`. The eMMC is a
   29.1G USB disk with model `RPi-MSD- 0001` and the CM4's serial number. Use
   its name (`/dev/sdX` below) in the following steps.

When you're finished, power off the HMI and **unplug the Micro USB cable**.
If the cable is still connected at the next power-on, the HMI goes back into
USB-boot mode instead of starting normally.

---

## 1. Creating the golden image

The result is a shrunk, compressed image file containing Raspberry Pi OS
**Bookworm Lite 64-bit** with EDATEC's kernel and drivers. It has a `pi` user,
SSH turned on and a fixed address on eth2. The HPC software is **not**
installed; section 2 does that.

Most people don't need this section. Use the existing image from
[Where the images are stored](#where-the-images-are-stored) and go to
[1.7](#17-flash-the-golden-image-onto-an-hmi). Rebuild the image only when the
OS or EDATEC drivers need updating.

Why Bookworm Lite:
- `HPC_LinuxGUI` is built against Bookworm's C library (see `readme.md`).
- EDATEC's Trixie (Debian 13) support is incomplete.
- The HMI program draws straight to the framebuffer, so no desktop is needed.

### 1.1 Write Bookworm Lite to the eMMC

1. Download the image and check its checksum. The 2026-10-06 release was used
   for the first build:
   ```bash
   mkdir -p ~/Downloads/pi-images && cd ~/Downloads/pi-images
   B=https://downloads.raspberrypi.com/raspios_oldstable_lite_arm64/images/raspios_oldstable_lite_arm64-2026-10-06/2026-10-06-raspios-bookworm-arm64-lite
   curl -fsSLO $B.img.xz.sha256 && curl -fsSLO $B.img.xz
   sha256sum -c 2026-10-06-raspios-bookworm-arm64-lite.img.xz.sha256
   ```
   The last command must print `OK`. Other releases are listed at
   <https://downloads.raspberrypi.com/>; `raspios_oldstable_*` is Bookworm
   (Legacy).
2. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop)).
3. Run `sudo rpi-imager` and choose Device **Raspberry Pi 4**, OS **Use custom**
   (then the `.img.xz`), and Storage **the `RPi-MSD- 0001` disk**. Click Write.
   - Imager 2.x **doesn't offer OS customisation (user, SSH) for custom images**.
     Its log shows `initFormat= ""`. That's expected; step 1.2 does the same job
     by hand.
   - If the first write fails with an async write error, write again. A
     successful write ends with matching `Hash of uncompressed image` and
     `Verify hash` lines.

### 1.2 Add the `pi` user and turn on SSH

Raspberry Pi OS reads two files from its boot partition on first boot: `ssh`
turns on the SSH server, and `userconf.txt` creates a user. Imager ejects the
disk when it finishes, so expose it again if needed, then:

```bash
udisksctl mount -b /dev/sdX1                  # the eMMC's boot partition ("bootfs")
cd /run/media/$USER/bootfs                    # check that config.txt and cmdline.txt are here
touch ssh
echo "pi:$(openssl passwd -6)" > userconf.txt # type the password when prompted
cd ~ && sync && udisksctl unmount -b /dev/sdX1
```

- The golden image uses **`pi` / `raspberry`**, the old Raspberry Pi default,
  on purpose. The golden image is only for development and as a starting point,
  and the provisioner deletes every login user except `nwhs`, so `pi` never
  reaches the field. When you log in, the HMI warns that the default password
  hasn't been changed; that's expected.
- Raspberry Pi OS gives this user passwordless sudo, which the provisioner
  needs.

Power off the HMI, **unplug the Micro USB cable**, connect Ethernet using the
[DHCP fallback](#fallback-the-laptop-as-a-dhcp-server), and power on. The first
boot expands the filesystem and reboots once. Then log in with `ssh pi@<ip>`.

### 1.3 Install EDATEC's drivers and kernel

The HMI needs internet for this step only. With the `hmi-direct` profile, the
laptop shares its own connection. Copies of EDATEC's scripts are kept in
[`golden_image/`](golden_image/) in case their URLs change.

```bash
# on the HMI
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-070c
```

According to [`golden_image/hmi2220-070c.json`](golden_image/hmi2220-070c.json),
this:
1. adds EDATEC's apt repository and installs `ed-linux-image-6.6.31-v8`,
   `ed-hmi2220-070c-firmware`, `ed-base-bsp-v8`, `ed-touchscreen-test`,
   `ed-reboot`, `ed-rtc`, `ed-qmi-tool`, `ed-usb-tools` and `ed-lvd`;
2. runs `kernel-change.sh 6.6.31-rpi-v8`, which copies EDATEC's kernel,
   initramfs, device trees and overlays into `/boot/firmware` and pins them in
   `/etc/default/raspi-firmware`;
3. puts every `linux-image*` package on hold, so an upgrade can't replace the
   kernel, and reboots.

**Known failure (it happened on the first build):** step 2 can silently do
nothing. `ed-install.sh` downloads `kernel-change.sh` with `curl -s` and pipes it
into `bash`, so a failed download runs an empty script and still "succeeds".
After the reboot you'll see:

- a black screen;
- `uname -r` showing `6.12.x+rpt-rpi-v8`;
- only HDMI outputs in `/sys/class/drm/`;
- an empty `/proc/fb`;
- no `KERNEL=` line in `/etc/default/raspi-firmware`.

**Fix:** run the kernel switch by hand, check it, then reboot:

```bash
# on the HMI (the script is also in golden_image/kernel-change.sh)
curl -fsSL https://apt.edatec.cn/downloads/202403/kernel-change.sh -o ~/kernel-change.sh
sudo bash ~/kernel-change.sh 6.6.31-rpi-v8

md5sum /boot/firmware/kernel8.img /boot/vmlinuz-6.6.31-rpi-v8      # the two sums must match
md5sum /boot/firmware/initramfs8 /boot/initrd.img-6.6.31-rpi-v8    # the two sums must match
grep -E '^(KERNEL|INITRAMFS)=' /etc/default/raspi-firmware         # both lines = 6.6.31-rpi-v8
ls /boot/firmware/overlays | grep -i edatec                        # vc4-kms-dsi-edatec-panel-*.dtbo
sudo reboot
```

If the HMI then doesn't boot, expose the eMMC and copy
`/boot/vmlinuz-6.12.*-rpi-v8` from the root partition over `kernel8.img` on the
boot partition. That puts the stock kernel back.

You can ignore these messages in `dmesg`:
- `imx219` probe errors (EDATEC's configuration enables a camera that isn't fitted);
- Bluetooth baud-rate timeouts;
- `mmc1: Failed to initialize a non-removable card`.

`ed-install.sh` also tries to copy a boot splash into
`/usr/share/plymouth/themes/pix/`, which doesn't exist on Lite. The only effect
is that there's no boot splash.

### 1.4 Check the hardware

After the reboot in 1.3, log in over SSH and run every check below before going
on. A unit that fails one here will fail in the field too. The "Expected"
column shows what the first build printed.

| # | Check | Command | Expected | If it fails |
| --- | --- | --- | --- | --- |
| 1 | Panel shows a console | Look at the screen | Boot messages, then a `login:` prompt within about 30 s | Run checks 2–4 to find out why |
| 2 | EDATEC kernel is running | `uname -r` | `6.6.31-rpi-v8` | `6.12.x+rpt-rpi-v8` means the kernel switch didn't happen; see the fix in 1.3 |
| 3 | Display driver created a framebuffer | `cat /proc/fb` | `0 vc4drmfb` | Empty means no panel driver. Do check 2, and confirm `config.txt` has `dtoverlay=vc4-kms-dsi-edatec-panel-rpi4,...` |
| 4 | Display outputs | `for c in /sys/class/drm/card*-*; do echo "$c: $(cat $c/status)"; done` | `card0-DSI-1: connected` (HDMI-A-1/2 `disconnected`, Writeback `unknown`) | Only HDMI and Writeback listed: same cause as check 3 |
| 5 | Touch controller detected | `grep -E '^(N\|H):' /proc/bus/input/devices` | `N: Name="10-0014 Goodix Capacitive TouchScreen"` with `H: Handlers=... event5` (the event number may differ) | No Goodix entry: check `sudo dmesg \| grep -i goodix`. The EDATEC packages or overlays may be missing |
| 6 | Touches register | `sudo apt install -y evtest`, then `sudo evtest /dev/input/event5`. Tap and drag; Ctrl+C stops it | `ABS_MT_POSITION_X`, `ABS_MT_POSITION_Y` and `BTN_TOUCH` lines scroll by while you touch, and nothing when you don't | No events: wrong `eventN`, or a cable or controller fault |
| 7 | EDATEC factory test is off | `systemctl is-enabled touch-test.service; systemctl is-active touch-test.service` | `disabled` and `inactive` | Run `sudo systemctl disable --now touch-test.service`. It would compete with `HPC_LinuxGUI` for the screen |

Without internet for `evtest`, this also works for check 6. It prints raw bytes
while you touch the screen, and nothing otherwise:

```bash
sudo timeout 10 cat /dev/input/event5 | xxd | head
```

If `systemctl` or `nmcli` says "terminal is not fully functional", that's your
SSH client's terminal type, not a fault. Run `export TERM=xterm-256color`, or
add `--no-pager`.

`touch-test.service` runs EDATEC's factory test program,
`/opt/ed-touchscreen-test/ed-touch-test`. The package has no command-line tool
we can use.

### 1.5 Prepare the image for cloning

Everything in this section is saved into the golden image, so it applies to
every HMI flashed from it.

#### Pre-checks

| Check | Command | Expected (first build) |
| --- | --- | --- |
| SSH keys will be regenerated on each clone | `systemctl --no-pager cat regenerate_ssh_host_keys.service` | The unit exists (from `raspberrypi-sys-mods`), has `Before=ssh.service` and runs `/usr/lib/raspberrypi-sys-mods/regenerate_ssh_host_keys` |
| Boot time before changes | `systemd-analyze; systemd-analyze blame --no-pager \| head` | `27.8s` total; `ed-lte-daemon.service` alone takes `20.0s`; `NetworkManager-wait-online` `6.2s` |
| EDATEC services | `systemctl --no-pager list-unit-files 'ed-*' '*lte*' '*qmi*'` | `ed-lte-daemon` enabled, `ed-net-monitor` disabled, `ed-usb-tools` enabled |
| Free space | `df -h /` | 29G, 2.3G used |

Don't delete the SSH host keys (in the cleanup below) unless the regeneration
unit exists. Without keys `ssh.service` fails, and the cloned HMIs can't be
reached over the network.

#### Turn off the LTE daemon

`ed-lte-daemon.service` waits for an optional cellular modem and adds about
20 s to every boot (also seen on the E180, see `dev_test/readme.md`). Turn it
off in the golden image:

```bash
sudo systemctl disable ed-lte-daemon.service && sudo reboot
systemd-analyze        # after the reboot
```

Expected: `14.1s` total and `multi-user.target reached after 3.7s in userspace`
(it was 27.8 s and 23.5 s). The slowest remaining item,
`NetworkManager-wait-online` (6.2 s), doesn't delay `multi-user.target`, and
provisioning turns it off.

On a unit that does use LTE, turn it back on with
`sudo systemctl enable ed-lte-daemon.service`.

#### Fixed address on the HPC port (eth2)

This gives eth2 the address `192.168.0.4/24`, so a technician can SSH in right
after flashing, before provisioning. The other two ports (eth0 and eth1) stay
on DHCP here; the HMI program sets them up when it runs.

The address is defined in one file,
[`BOOKWORM/network/eth2-hpc.nmconnection`](BOOKWORM/network/eth2-hpc.nmconnection).
It's installed by hand here, and `stock-hmi.py` installs it again every time it
runs.

The profile picks the port by its **hardware path**, not by the name `eth2` or
its MAC address:

| Name (first build) | Hardware | `ID_PATH` | Role |
| --- | --- | --- | --- |
| eth0 | CM4 built-in, `bcmgenet` | `platform-fd580000.ethernet` | bridge |
| eth1 | Realtek RTL8153 USB, `r8152` | `platform-fd500000.pcie-pci-0000:01:00.0-usb-0:2:1.0` | bridge |
| **eth2** | Realtek RTL8153 USB, `r8152` | `platform-fd500000.pcie-pci-0000:01:00.0-usb-0:3:1.0` | **HPC controller, 192.168.0.4** |

eth1 and eth2 are two USB network chips, so their names follow the order in
which USB finds them and could swap between boots. MAC addresses differ from
unit to unit. The `ID_PATH` is the same on every HMI2220-070C.

TODO: record which labelled socket on the case is `usb-0:3` (eth2), for
technicians.

To collect the table above on a unit:

```bash
for i in /sys/class/net/eth*; do echo "== ${i##*/} mac=$(cat $i/address)"; udevadm info -q property -p $i | grep -E '^(ID_PATH|ID_NET_DRIVER|ID_BUS|ID_MODEL|ID_VENDOR)='; done
ip -br link        # the port with a cable in it shows UP / LOWER_UP
```

Install the profile on the HMI while you're still connected through the DHCP
fallback:

```bash
# on the laptop, from this repo (note the ':' at the end)
scp BOOKWORM/network/eth2-hpc.nmconnection pi@192.168.1.<x>:
# on the HMI
sudo install -m 600 -o root -g root ~/eth2-hpc.nmconnection /etc/NetworkManager/system-connections/
rm ~/eth2-hpc.nmconnection
sudo nmcli con reload
sudo reboot
```

Move the cable to eth2, reconnect on `192.168.0.4` with the
[normal method](#normal-method-the-hpc-port-eth2-at-19216804), and check:

| Check | Command | Expected (first build) |
| --- | --- | --- |
| Profile active on eth2 | `nmcli -f NAME,DEVICE con show --active` | `eth2-hpc  eth2` |
| Address | `ip -br addr show eth2` | `eth2 UP 192.168.0.4/24 fe80::…/64` |
| Right socket | `udevadm info -q property -p /sys/class/net/eth2 \| grep ID_PATH` | `…-usb-0:3:1.0` |

If the profile isn't active, check that the file has mode `600` and is owned by
root (NetworkManager ignores it otherwise), and that the `ID_PATH` matches the
file's `[match] path=` line.

**How this interacts with the HMI program.** Every time `HPC_LinuxGUI` starts,
it deletes and recreates its own `eth2-hpc` profile, along with a `br0` bridge
over eth0 and eth1
(`HPC_Firmware/LinuxHMI/HPC_LinuxGUI/src/system/network_config_nmcli.cpp`). Our
profile uses the same name, so the app replaces it rather than competing with
it.

- The app's eth2 address was changed from `.1` to `.4` on 2026-10-22, on
  `HPC_Firmware` branch `eth2-static-192.168.0.4`. App v2.0.8 and earlier still
  set eth2 to `.1` when they start, as seen in [2.3](#23-check-the-provisioned-hmi).
  TODO: release an app build with the `.4` change.
- The controller still uses `192.168.0.1` as its **gateway**
  (`HPC_Firmware/iot/src/ethernet_vars.h`). TODO: change it to `.4` for
  anything the controller routes through the HMI.
- The app picks the port by name (`ifname eth2`). If the two USB network chips
  are ever found in the other order, its address and the bridge end up on the
  wrong sockets. Matching by `ID_PATH`, as our profile does, avoids that.
  TODO: consider the same in the app.

#### Clean up before capturing

Remove everything that is unique to this unit, so every HMI flashed from the
image is distinct. This must be the **last** thing you do before capturing.
**Don't boot the HMI again before 1.6**: booting recreates the keys and the
machine ID.

The `regenerate_ssh_host_keys` service (checked in the pre-checks) deletes the
keys, runs `ssh-keygen -A` and then disables itself, so it runs exactly once, on
each clone's first boot. The keys are also deleted here so that no private key
ends up in the image file.

```bash
# on the HMI
sudo apt clean
sudo systemctl enable regenerate_ssh_host_keys.service
sudo rm -f /etc/ssh/ssh_host_*
sudo truncate -s 0 /etc/machine-id                       # systemd creates a new one on first boot
ls -l /var/lib/dbus/machine-id                           # should be a symlink to /etc/machine-id
sudo rm -f /var/lib/NetworkManager/*.lease
rm -f ~/kernel-change.sh
```

Check the cleanup, then power off without leaving shell history behind:

```bash
systemctl is-enabled regenerate_ssh_host_keys.service   # enabled
ls /etc/ssh/ssh_host_* 2>&1                             # No such file or directory
wc -c < /etc/machine-id                                 # 0
systemctl is-enabled ed-lte-daemon.service              # disabled
ls -l /etc/NetworkManager/system-connections/           # only eth2-hpc.nmconnection, -rw------- root root
ls -l /boot/firmware/userconf.txt                       # No such file (it held a password hash)

unset HISTFILE; rm -f ~/.bash_history; sudo poweroff
```

TODO: turn this cleanup into a script in the repo, so it can't be done
partially.

### 1.6 Capture and shrink the image

Name the image after the build date: `hpc-golden-YYYY-MM-DD.img`. The first
build is `hpc-golden-2026-10-22.img`. You need about 32 GB of free disk space
for the copy.

1. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop)).
   The desktop may mount the boot partition automatically. Unmount it, and don't
   mount anything else:
   ```bash
   udisksctl unmount -b /dev/sdX1
   lsblk /dev/sdX          # the MOUNTPOINTS column must be empty
   ```
   If the unmount says "target is busy", close any file manager window showing
   the disk and try again.
2. Copy the whole eMMC to a file. **`if=` (input) is the eMMC and `of=`
   (output) is the file.** If you swap them, the file overwrites the eMMC.
   ```bash
   sudo dd if=/dev/sdX of=hpc-golden-2026-10-22.img bs=4M status=progress conv=fsync
   sudo chown $USER: hpc-golden-2026-10-22.img
   ```
3. Shrink and compress it with [PiShrink](https://github.com/Drewsif/PiShrink).
   PiShrink shrinks the filesystem to its contents, arranges for it to expand
   back to full size on first boot, and with `-Z` compresses the result with xz.
   `-a` uses all CPU cores.
   ```bash
   sudo pishrink.sh -Z -a hpc-golden-2026-10-22.img    # writes .img.xz and removes the .img
   sha256sum hpc-golden-2026-10-22.img.xz > hpc-golden-2026-10-22.img.xz.sha256
   ls -lh hpc-golden-2026-10-22.img*
   ```
   Output from the first build (PiShrink v26.03.16):
   ```
   pishrink.sh: An existing /etc/rc.local was not found, autoexpand may fail...
   Creating new /etc/rc.local
   rootfs: 64723/1810016 files (0.2% non-contiguous), 679388/7500800 blocks
   Resizing the filesystem on /dev/loop0 to 825439 (4k) blocks.
   pishrink.sh: Zeroed 950M
   pishrink.sh: Shrunk hpc-golden-2026-10-22.img.xz from 30G to 507M in 1m 30s
   ```
   - The `rc.local` warning is expected: Bookworm doesn't have one, so PiShrink
     creates its own to expand the filesystem on first boot. 1.7 checks that it
     worked.
   - If the "Checking filesystem" step reports errors, the copy is bad. Redo
     step 2.
4. Upload the `.img.xz` and its `.sha256` file to the image storage (see
   [Where the images are stored](#where-the-images-are-stored)). Never replace
   an existing image; upload a new one with a new date.
5. Record the image's contents next to it. For the first build:

   | Item | Value |
   | --- | --- |
   | File | `hpc-golden-2026-10-22.img.xz`, 507M |
   | SHA-256 | `dcf8cf1403c065be78ce5aad20b8625a58395161cd887240d99ba2af0d2e0020` |
   | Pi OS release | `2026-10-06-raspios-bookworm-arm64-lite` |
   | Kernel | `6.6.31-rpi-v8` (EDATEC `ed-linux-image-6.6.31-v8`, held) |
   | Login | `pi` / `raspberry` |

   EDATEC packages, from `dpkg -l 'ed-*'` on the first flashed HMI:

   | Package | Version |
   | --- | --- |
   | `ed-base-bsp-v8` | 2:1.20260508.1 |
   | `ed-hmi2220-070c-firmware` | 1.20241204.1 |
   | `ed-linux-image-6.6.31-v8` | 2:1.20250716.1 |
   | `ed-lvd` | 1.20260522.1 |
   | `ed-qmi-tool` | 2.0.4 |
   | `ed-reboot` | 1.20250704.1 |
   | `ed-rtc` | 1.20250620.1 |
   | `ed-touchscreen-test` | 1.20250731.1 |
   | `ed-usb-tools` | 1.20250912 |

#### Where the images are stored

The current golden image is in this Google Drive folder:

- Folder: <https://drive.google.com/drive/folders/1tibp_miz9kWSzZj1l7MBG5oEfH0VU8Kn?usp=drive_link>
- `hpc-golden-2026-10-22.img.xz`: <https://drive.google.com/file/d/1WYvcbQXtD-RB6T1y32ddFpm1zrGR32Wt/view?usp=drive_link>

This location is temporary and may move. If a link stops working, ask the
maintainer for the current location and update this section.

TODO: create a formal storage place for images (golden images and, later,
release images), with a fixed folder per image type, the `.sha256` beside every
file, and a rule that files are never replaced, only added.

### 1.7 Flash the golden image onto an HMI

A technician can do this offline. You need the `.img.xz`, its `.sha256` file and
the `rpiboot-msd-cm4/` loader folder.

1. Check that the image file is complete and unchanged:
   ```bash
   sha256sum -c hpc-golden-2026-10-22.img.xz.sha256      # must print OK
   ```
2. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop)).
3. Write the image. Either use `sudo rpi-imager` (**Use custom**, the golden
   `.img.xz`, the `RPi-MSD- 0001` disk, Write; no customisation is needed,
   because the image already has `pi` and SSH), or use `dd`:
   ```bash
   xzcat hpc-golden-2026-10-22.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
   ```
   With `dd`, the progress line reaches about 3.9 GB within seconds and then
   seems to hang with no prompt. That's expected. The data went into the
   laptop's memory first, and `conv=fsync` makes `dd` wait while it's written to
   the eMMC at only about 5 MB/s, which takes roughly 12 minutes. To watch the
   remaining amount fall, run this in another terminal:
   ```bash
   watch -n5 grep -e Dirty -e Writeback: /proc/meminfo
   ```
   Don't unplug anything until the prompt returns. On the first flash it ended
   with:
   ```
   0+118057 records in
   0+118057 records out
   3926258176 bytes (3.9 GB, 3.7 GiB) copied, 743.663 s, 5.3 MB/s
   ```
   The byte count must be `3926258176` for this image. `0+N records` is normal
   when reading from a pipe.
4. Power off the HMI, unplug the Micro USB cable, plug the laptop into eth2 and
   power on. The panel should show a console within about 30 s. The first boot
   expands the filesystem.
5. Check the result from the laptop, using the
   [normal method](#normal-method-the-hpc-port-eth2-at-19216804):

   | Check | Command | Expected (first flash) |
   | --- | --- | --- |
   | Reachable, with a new host key | `ssh-keygen -R 192.168.0.4; ssh pi@192.168.0.4` | `The authenticity of host '192.168.0.4' can't be established. ED25519 key fingerprint is …`, then a `pi@raspberrypi` prompt |
   | Filesystem expanded | `df -h /` | `/dev/mmcblk0p2   29G  2.1G   25G   8% /` |
   | Unique machine ID | `cat /etc/machine-id` | 32 hex characters, different on each HMI |
   | Kernel | `uname -r` | `6.6.31-rpi-v8` |
   | Display | `cat /proc/fb` | `0 vc4drmfb` |
   | eth2 profile | `nmcli -f NAME,DEVICE con show --active` | `eth2-hpc  eth2` and `lo  lo` |
   | EDATEC packages | `dpkg -l 'ed-*'` | 9 packages, all `ii`, with the versions listed in 1.6 |

   If `df` shows about 3G instead of 29G, the filesystem didn't expand. Expand
   it by hand with `sudo raspi-config nonint do_expand_rootfs && sudo reboot`.

---

## 2. Provisioning an HMI from the golden image

Provisioning turns a freshly flashed golden image into a working HPC HMI. It
installs the app, creates the `nwhs` user, configures the network and startup
services, and removes the `pi` user. It works offline: the technician needs a
laptop, an Ethernet cable and the provisioning USB.

### 2.1 Build the provisioning USB

The maintainer does this on a PC with `stock_hmi` and `hpc-releases` checked
out side by side (for example `~/nwhs/stock_hmi` and `~/nwhs/hpc-releases`).

1. Update both checkouts (`git pull`), and make sure `stock_hmi` has no
   uncommitted changes.
2. Plug in a FAT32 or exFAT USB stick. The stick doesn't have to be empty: the
   script only adds its own files and folders, and `--replace` only removes
   those.
3. Build the kit, using the stick's mount point:
   ```bash
   cd stock_hmi
   ./make-usb-kit.py /run/media/$USER/<USB>              # the release named in hpc-releases/CURRENT
   ./make-usb-kit.py /run/media/$USER/<USB> --release v2.0.8 --replace   # a specific release, replacing an old kit
   ```
   The script checks the app binary against the release's SHA-256 before
   copying anything, then prints what went into the kit. For example:
   ```
   built:     2026-10-23T16:20:29Z
   app:       v2.0.8 (hmi_v2.0.8.bin)
   stock_hmi: 2507e7e
   releases:  a808bf7
   ```
   If the `stock_hmi` line ends in `-dirty`, the checkout had uncommitted
   changes. Commit them and rebuild, so the kit can be traced to a commit.
4. Unmount the stick (close any file manager window showing it first):
   ```bash
   udisksctl unmount -b /dev/sdX1
   ```

The kit contains:

```text
USB/
├── stock-hmi.py
├── bin/          # HPC_LinuxGUI, assets/, release-manifest.json
├── debs/         # offline packages: iptables, libip6tc2, libpaho-mqtt1.3
├── network/      # eth2-hpc.nmconnection: eth2 = 192.168.0.4
├── KIT.txt       # what went into the kit (shown above)
└── SHA256SUMS    # a checksum for every file (331 for v2.0.8)
```

There's no `settings.txt` in the kit. The app creates its own on first start.

If the technician will also flash the HMI, copy the golden image, its `.sha256`
file and the `rpiboot-msd-cm4/` folder onto the stick by hand.

### 2.2 Run the provisioner

The golden image has no desktop, so everything is done over SSH.

1. Plug the laptop into the HMI's eth2 socket and log in:
   ```bash
   nmcli con up hmi-eth2
   ssh pi@192.168.0.4                   # password: raspberry
   ```
2. Check that the tools the provisioner uses are present. Each line should show
   a path, as it did on the 2026-10-22 golden image. If any says `MISSING`,
   stop: the provisioner would fail partway through.
   ```bash
   for c in rsync setcap ldd visudo nmcli udevadm hostnamectl python3; do printf '%-12s %s\n' $c "$(command -v $c || echo MISSING)"; done
   ```
3. Plug the USB stick into the HMI, mount it, and check the kit:
   ```bash
   lsblk                                # find the stick, e.g. sda1
   sudo mount /dev/sda1 /mnt
   cd /mnt
   cat KIT.txt                          # is this the release you expect?
   sha256sum -c --quiet SHA256SUMS && echo KIT OK
   ```
   `KIT OK` means every file arrived intact. Any `FAILED` line means the stick
   is damaged or was changed; rebuild it.
4. Run the provisioner:
   ```bash
   sudo python3 ./stock-hmi.py
   ```
   It takes about 15 seconds and finishes by rebooting the HMI, which closes
   your SSH session. The first successful run printed (shortened):
   ```
   Installing runtime packages
   Setting up libip6tc2:arm64 (1.8.9-2) ...
   Setting up libpaho-mqtt1.3:arm64 (1.3.12-1) ...
   Setting up iptables (1.8.9-2) ...
   Running: useradd --create-home --user-group --shell /bin/bash nwhs
   Running: /usr/bin/rsync -a --delete --exclude=/settings.txt --chown=nwhs:nwhs /mnt/bin/ /home/nwhs/hpc-hmi/bin/
   ldd output:
       libpaho-mqtt3a.so.1 => /lib/aarch64-linux-gnu/libpaho-mqtt3a.so.1
       libudev.so.1 => /lib/aarch64-linux-gnu/libudev.so.1
       ...
   /etc/sudoers.d/nwhs-hpc: parsed OK
   Created symlink /etc/systemd/system/multi-user.target.wants/hmi.service → /etc/systemd/system/hmi.service.
   Running: usermod --lock pi
   Legacy users to remove on reboot: pi
   Provisioning completed successfully
   The system will reboot in five seconds
   Connection to 192.168.0.4 closed by remote host.
   ```
   Two lines look like errors but are harmless: `usermod: no changes`, and
   `Failed to disable unit: Unit file display-manager.service does not exist`
   (Lite has no desktop).

**If it stops at "Installing runtime packages"** with `dpkg: dependency
problems`, one of the bundled packages needs other packages that aren't on the
golden image. Nothing else has been changed at that point. To recover:

1. Remove the half-installed package: `sudo dpkg --purge <name>`.
2. Check the package database is clean: `sudo dpkg --audit` should print
   nothing.
3. Fix `BOOKWORM/debs/` in this repo, rebuild the kit and run the provisioner
   again.

This is how `libx11-dev` was found and removed. It's only needed to compile
the app, not to run it.

What the provisioner does, in order:

1. installs the packages from `debs/`;
2. creates the `nwhs` user with the standard password, in the `sudo`, `video`,
   `input` and other hardware groups;
3. copies `bin/` to `/home/nwhs/hpc-hmi/bin/`, checks with `ldd` that every
   library the app needs is present, and gives `HPC_LinuxGUI` permission to
   change network settings (`cap_net_admin,cap_net_raw`);
4. sets the hostname to `hpc`;
5. installs `network/eth2-hpc.nmconnection` again, so eth2 is `192.168.0.4`
   even if something changed it;
6. lets `nwhs` use sudo (with a password) and run `nmcli` and `ip` without one;
7. adds a udev rule that creates `/dev/input/touchscreen`;
8. installs `hmi.service` (runs `HPC_LinuxGUI 192.168.0.2`) and
   `hmi-console.service`, sets up autologin on the panel, starts in text mode
   (`multi-user.target`) and keeps SSH on;
9. locks every login user except `nwhs` (on the golden image, that's `pi`) and
   **deletes them on the next boot**, along with their sudo rules;
10. logs everything to `/var/log/hpc-stock-installer.log`, then reboots.

### 2.3 Check the provisioned HMI

After the reboot, log in as `nwhs`. The `pi` user no longer exists.

**Reaching the HMI with app v2.0.8 or earlier.** These versions move eth2 to
`192.168.0.1` when the app starts. Many routers also use that address, so on a
laptop that's also on Wi-Fi, turn Wi-Fi off and use a profile for the whole
`192.168.0.x` range:

```bash
nmcli radio wifi off
nmcli con add type ethernet con-name hmi-eth2-wide ifname eno1 ipv4.method manual \
  ipv4.addresses 192.168.0.100/24 ipv4.never-default yes ipv6.method link-local
nmcli con up hmi-eth2-wide
ssh nwhs@192.168.0.1
```

When you're done, get Wi-Fi back with
`nmcli con down hmi-eth2-wide; nmcli radio wifi on`. An app built with the `.4`
change keeps eth2 at `192.168.0.4`, so the normal method works.

SSH shows the same host key as before provisioning, under a different address.
That's expected: provisioning doesn't change the keys.

| Check | Command (as `nwhs`) | Expected (first run, app v2.0.8) |
| --- | --- | --- |
| Panel | Look at it and touch it | The HPC GUI is shown, and touch works |
| Hostname | `hostname` | `hpc` |
| `pi` removed | `getent passwd pi \|\| echo "pi removed"` | `pi removed` |
| App running | `systemctl --no-pager status hmi.service \| head -5` | `Active: active (running)`, since boot |
| Network profiles | `nmcli -f NAME,DEVICE con show --active` | `br0 br0`, `eth2-hpc eth2`, `lo lo`, `br0-port1 eth0`, `br0-port2 eth1` (the app creates the `br0` profiles) |
| eth2 address | `nmcli -g ipv4.addresses con show eth2-hpc` | `192.168.0.1/24` with v2.0.8. TODO: confirm `192.168.0.4/24` with an app built with the `.4` change |
| App files | `ls -l ~/hpc-hmi/bin/` | `assets/`, `HPC_LinuxGUI`, `release-manifest.json`, and `settings.txt`, which the app created when it first started |
| Installer log | `sudo grep -iE 'error\|fail' /var/log/hpc-stock-installer.log` | Nothing from the successful run. The log keeps every run, so errors from earlier failed runs still show |

---

## 3. Updating the HMI software

An update is a new provisioning USB containing the new app release, run on an
already provisioned HMI.

### 3.1 Maintainer: build a kit with the new release

TODO: not yet done with a release newer than v2.0.8.

1. Publish the new release to `hpc-releases` (see that repo's README) and
   update its `CURRENT` file if this release should become the default.
2. Pull `hpc-releases`, then build a kit as in [2.1](#21-build-the-provisioning-usb).
   The kit takes the app straight from `hpc-releases`; there's no separate
   update command.

### 3.2 Technician: apply the kit to a provisioned HMI

TODO: not yet run on hardware. In particular, confirm that the unit's
`settings.txt` survives: note `sha256sum ~/hpc-hmi/bin/settings.txt` before the
run, and compare it afterwards. If it changed, check the file's time with
`ls -l`; a time after the reboot means the app rewrote it, not the provisioner.

Running the provisioner again is the update. It copies `bin/` from the USB over
`/home/nwhs/hpc-hmi/bin/` and **deletes any other file in that folder**, with
one exception: `settings.txt`, which holds this unit's configuration, is never
replaced or deleted. It then rewrites the services and reboots.

```bash
ssh nwhs@192.168.0.4                # or 192.168.0.1 while the HMI runs app v2.0.8 or earlier (see 2.3)
sudo mount /dev/sda1 /mnt && cd /mnt
cat KIT.txt; sha256sum -c --quiet SHA256SUMS && echo KIT OK
sudo python3 ./stock-hmi.py         # use sudo directly: nwhs needs a password for sudo
```

Then do the checks in [2.3](#23-check-the-provisioned-hmi), and confirm the new
version with `grep release_version ~/hpc-hmi/bin/release-manifest.json`.

The bundled packages are built for Bookworm. On a unit with a different OS
(for example Trixie), `dpkg` may refuse them; flashing the golden image first
avoids this. An experimental `--patch` mode for later OS changes, such as log
rotation, is in `dev_test/stock-hmi2.py` (see `dev_test/TODO.md`).

---

## Open items

| Item | Where |
| --- | --- |
| Create a formal storage place for golden and release images; the current Google Drive folder may move | [1.6](#where-the-images-are-stored) |
| Release an `HPC_LinuxGUI` build with eth2 at `192.168.0.4` (`HPC_Firmware` branch `eth2-static-192.168.0.4`), then confirm the 2.3 eth2 check | [1.5](#fixed-address-on-the-hpc-port-eth2), [2.3](#23-check-the-provisioned-hmi) |
| Change the controller's gateway to `192.168.0.4` in `HPC_Firmware/iot/src/ethernet_vars.h` | [1.5](#fixed-address-on-the-hpc-port-eth2) |
| Record which labelled socket on the case is eth2 (`usb-0:3`) | [1.5](#fixed-address-on-the-hpc-port-eth2) |
| Test the update path (3.2), including that `settings.txt` survives | [3.2](#32-technician-apply-the-kit-to-a-provisioned-hmi) |
| Script the pre-capture cleanup | [1.5](#clean-up-before-capturing) |
| Give `stock_hmi` a version (`VERSION` file, `setup-v1.0.0` tag) and record the golden, setup and app versions in `/etc/hpc-release` on each unit | `readme.md` |
| Try the Windows "Internet Connection Sharing" fallback | [0](#fallback-the-laptop-as-a-dhcp-server) |
| Build `HPC_HMI_Provissioning.pdf` from the updated `HPC_HMI_Provissioning.tex` (the old PDF described the desktop double-click process and was removed) | `HPC_HMI_Provissioning.tex` |
