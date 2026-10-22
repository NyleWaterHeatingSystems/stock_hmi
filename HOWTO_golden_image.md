# HPC HMI: Golden Image, Provisioning, and Updates

How-to for the EDATEC **ED-HMI2220-070C** (Raspberry Pi **Compute Module 4**,
29.1 GiB eMMC) used as the HPC HMI. It documents how the golden image was built
and how to reproduce every step.

| Section | Who | Network |
| --- | --- | --- |
| [1. Creating the golden image](#1-creating-the-golden-image) | Maintainer, at the shop | Internet needed once (EDATEC drivers) |
| [2. Provisioning an HMI](#2-provisioning-an-hmi-from-the-golden-image) | Technician, in the field | **Offline**: laptop + Ethernet cable + USB |
| [3. Updating the HMI software](#3-updating-the-hmi-software) | Maintainer, then technician | Internet for the maintainer only |

> **Status legend:** ✅ done and verified on hardware · ⏳ written down but not
> yet verified on hardware. Update the markers as steps are proven.

---

## 0. Background and one-time laptop setup

### Hardware facts

- `cat /proc/device-tree/model` → `Raspberry Pi Compute Module 4 Rev 1.1`
- The OS lives on **eMMC** (embedded MultiMediaCard: flash soldered to the
  board). There is no SD card to pull. `mmcblk0boot0/1` in `lsblk` confirm eMMC.
- To write the eMMC from a PC, the CM4 is put in **USB-boot mode** and `rpiboot`
  makes the eMMC appear as a USB disk. On this HMI there is **no boot switch or
  jumper**. If the Micro USB port is connected to a PC at power-on, the HMI enters
  USB-boot mode.
- The EDATEC display and touch need **EDATEC's 6.6.31 kernel**. The stock Raspberry
  Pi OS kernel (6.12.x) boots, but the screen stays black.

### Laptop tools (Arch Linux shown; adapt for your distro) ✅

```bash
sudo pacman -S rpi-imager dnsmasq
yay -S rpiusbboot            # AUR; builds github.com/raspberrypi/usbboot, installs `rpiboot`
```

**rpiboot loader for the CM4 (important).** The current `usbboot` release's
default loader (`mass-storage-gadget64`) gets the CM4 started but the eMMC
**never appears** on this HMI. The `msd` loader in the current release has no
CM4 files. Use the older firmware-based loader from release `20221215-105525`:

```bash
mkdir -p ~/rpiboot-msd-cm4 && cd ~/rpiboot-msd-cm4
base=https://raw.githubusercontent.com/raspberrypi/usbboot/20221215-105525
curl -fsSLO $base/msd/bootcode.bin
curl -fsSLO $base/msd/start.elf
curl -fsSLO $base/msd/start4.elf
# msd/bootcode4.bin is a git symlink, so fetch the real file from the repo root:
curl -fsSLo bootcode4.bin $base/bootcode4.bin
ls -la    # bootcode4.bin must be 106008 bytes, not 16
```

Put this folder on the technician USB too, because the technician has no internet.

### Direct-cable networking: laptop ↔ HMI, no Wi-Fi, no router ✅

A fresh HMI asks for an address by DHCP. On a direct cable nothing answers
unless the laptop does. A NetworkManager **shared** profile makes the laptop the
DHCP server. It does **not** need internet.

```bash
sudo ip addr flush dev eno1          # only if an address was added by hand earlier
nmcli con add type ethernet ifname eno1 con-name hmi-direct \
  ipv4.method shared ipv4.addresses 192.168.1.200/24 \
  ipv6.method link-local
nmcli con up hmi-direct
```

(Replace `eno1` with the laptop's Ethernet interface: `ip -br link`.)

Find the HMI after it boots:

```bash
cat /var/lib/NetworkManager/dnsmasq-eno1.leases   # look for "raspberrypi" / "hpc"
ssh pi@192.168.1.<x>
```

Fallback with no IPv4 at all, using IPv6 link-local:

```bash
ping -6 -c3 ff02::1%eno1                  # every device on the cable replies
ssh pi@fe80::xxxx:xxxx:xxxx:xxxx%eno1
```

`.local` names (`raspberrypi.local`) only work if the laptop runs mDNS
(avahi + `nss-mdns`). Do not rely on them.

Windows laptops: "Internet Connection Sharing" does the same job. The HMI then
gets a `192.168.137.x` address. ⏳

### Procedure: expose the eMMC on the laptop (used in 1.1 and 1.5) ✅

1. Connect a **data-capable** Micro USB → USB-A cable from the HMI's Micro USB
   port to the laptop. Keep normal power on the DC 2-pin Phoenix terminal.
2. Start the loader **first**, and leave it waiting:
   ```bash
   sudo rpiboot -v -d ~/rpiboot-msd-cm4
   ```
3. Power-cycle the HMI at the DC terminal. The HMI only checks for USB boot at
   power-on.
4. After about 10 s, run `lsblk -o NAME,SIZE,TRAN,MODEL,SERIAL`. The eMMC shows as
   a ~29.1G USB disk, model `RPi-MSD- 0001`, with a serial matching the CM4.
   **Unplug other USB drives first.** A 29.1G thumbdrive looks nearly identical.

---

## 1. Creating the golden image

Result: a shrunk, compressed `.img` with Raspberry Pi OS **Bookworm Lite
64-bit** and EDATEC's drivers and kernel. It has a temporary `pi` user and SSH
enabled, and the HPC software is **not** installed. Section 2 provisions it.

Why Bookworm Lite:
- `HPC_LinuxGUI` is built against Bookworm's glibc (see `readme.md`).
- EDATEC's Trixie support is incomplete.
- The HMI runs straight on the framebuffer, so a desktop is unnecessary.
  `stock-hmi.py` switches to `multi-user.target` anyway.

### 1.1 Write Bookworm Lite to the eMMC ✅

1. Download and verify the image (the 2026-10-06 release was used):
   ```bash
   mkdir -p ~/Downloads/pi-images && cd ~/Downloads/pi-images
   B=https://downloads.raspberrypi.com/raspios_oldstable_lite_arm64/images/raspios_oldstable_lite_arm64-2026-10-06/2026-10-06-raspios-bookworm-arm64-lite
   curl -fsSLO $B.img.xz.sha256 && curl -fsSLO $B.img.xz
   sha256sum -c 2026-10-06-raspios-bookworm-arm64-lite.img.xz.sha256
   ```
   Browse other releases at <https://downloads.raspberrypi.com/>.
   `raspios_oldstable_*` = Bookworm (Legacy).
2. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop-used-in-11-and-15)).
3. `sudo rpi-imager` → Device **Raspberry Pi 4** → OS **Use custom** →
   the `.img.xz` → Storage: the `RPi-MSD- 0001` disk → Write.
   - Imager 2.x **does not offer OS customisation for "Use custom" images**. Its
     log shows `initFormat= ""`. That is expected; step 1.2 replaces it.
   - If the first write fails with an async write error, write again. A
     successful run ends with matching `Hash of uncompressed image` and
     `Verify hash` lines.

### 1.2 Add the temporary user and enable SSH ✅

Imager ejects the disk at the end, so expose it again if needed. Then:

```bash
udisksctl mount -b /dev/sdX1                  # the eMMC's bootfs partition
cd /run/media/$USER/bootfs                    # confirm config.txt and cmdline.txt are here
touch ssh
echo "pi:$(openssl passwd -6)" > userconf.txt # prompts for the temporary password
cd ~ && sync && udisksctl unmount -b /dev/sdX1
```

- Name the user **`pi`**. `stock-hmi.py` removes every regular login user
  except `nwhs` during provisioning (the `detect-legacy-users` branch).
  On older versions, only `pi` is removed.
- Pi OS gives this user passwordless sudo. `stock-hmi.py` needs that.
- Store the temporary password in the team password store, not in this repo.

Exit `rpiboot`, **unplug the Micro USB cable** (or the HMI re-enters USB-boot),
connect Ethernet, and power-cycle. First boot expands the filesystem and reboots
once. Then `ssh pi@<ip>` ([networking above](#direct-cable-networking-laptop--hmi-no-wi-fi-no-router)).

### 1.3 Install EDATEC drivers and kernel ✅ (with a manual fix)

The HMI needs internet for this step only. With the `hmi-direct` profile, the
laptop shares its own connection. EDATEC's scripts are copied in
[`golden_image/`](golden_image/) in case their URLs change.

```bash
# on the HMI
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-070c
```

What it does, per [`golden_image/hmi2220-070c.json`](golden_image/hmi2220-070c.json):
1. Adds EDATEC's apt repo and installs `ed-linux-image-6.6.31-v8`,
   `ed-hmi2220-070c-firmware`, `ed-base-bsp-v8`, `ed-touchscreen-test`, `ed-reboot`,
   `ed-rtc`, `ed-qmi-tool`, `ed-usb-tools` and `ed-lvd`.
2. Runs `kernel-change.sh 6.6.31-rpi-v8`, which copies EDATEC's kernel, initramfs,
   DTBs and overlays into `/boot/firmware` and pins them in
   `/etc/default/raspi-firmware`.
3. Puts every `linux-image*` package on hold, then reboots.

**Known failure (seen on this build):** step 2 silently did nothing. `ed-install.sh`
pipes `curl -s` into `bash`, so a failed download runs an empty script and
"succeeds". The symptoms after reboot are:

- the screen stays black;
- `uname -r` shows `6.12.x+rpt-rpi-v8`;
- `/sys/class/drm/` only lists HDMI outputs;
- `/proc/fb` is empty;
- `/etc/default/raspi-firmware` has no `KERNEL=` line.

**Fix:** run the kernel switch by hand, check it, then reboot.

```bash
# on the HMI (the script is also at golden_image/kernel-change.sh)
curl -fsSL https://apt.edatec.cn/downloads/202403/kernel-change.sh -o ~/kernel-change.sh
sudo bash ~/kernel-change.sh 6.6.31-rpi-v8

md5sum /boot/firmware/kernel8.img /boot/vmlinuz-6.6.31-rpi-v8      # must match
md5sum /boot/firmware/initramfs8 /boot/initrd.img-6.6.31-rpi-v8    # must match
grep -E '^(KERNEL|INITRAMFS)=' /etc/default/raspi-firmware         # both = 6.6.31-rpi-v8
ls /boot/firmware/overlays | grep -i edatec                        # vc4-kms-dsi-edatec-panel-*.dtbo
sudo reboot
```

Recovery if it does not boot: expose the eMMC and copy
`/boot/vmlinuz-6.12.*-rpi-v8` from rootfs over `kernel8.img` on bootfs.

Harmless noise in `dmesg`:
- `imx219` probe errors (EDATEC's config enables a camera that isn't fitted);
- Bluetooth baud-rate timeouts;
- `mmc1: Failed to initialize a non-removable card`.

`ed-install.sh` also tries to copy a splash to
`/usr/share/plymouth/themes/pix/`, which does not exist on Lite. Only the boot
splash is lost.

### 1.4 Verify the hardware ✅

Run these checks over SSH after the reboot in 1.3. Do every one before going
on. A unit that fails one will fail in the field too. Results from the first
build are in the "Expected" column.

| # | Check | Command | Expected (pass) | If it fails |
| --- | --- | --- | --- | --- |
| 1 | Panel shows a console | look at the screen | Boot messages, then a `login:` prompt within ~30 s | Run checks 2–4 to find out why |
| 2 | EDATEC kernel is running | `uname -r` | `6.6.31-rpi-v8` | `6.12.x+rpt-rpi-v8` means the kernel switch did not happen; see the 1.3 fix |
| 3 | Display driver created a framebuffer | `cat /proc/fb` | `0 vc4drmfb` | Empty: no panel driver. Check 2, and confirm `config.txt` has `dtoverlay=vc4-kms-dsi-edatec-panel-rpi4,...` |
| 4 | Display outputs | `for c in /sys/class/drm/card*-*; do echo "$c: $(cat $c/status)"; done` | `card0-DSI-1: connected` (HDMI-A-1/2 `disconnected`, Writeback `unknown`) | Only HDMI and Writeback listed: same cause as 3 |
| 5 | Touch controller detected | `grep -E '^(N\|H):' /proc/bus/input/devices` | `N: Name="10-0014 Goodix Capacitive TouchScreen"` with `H: Handlers=... event5` (the event number may differ) | No Goodix entry: check `sudo dmesg \| grep -i goodix`; the EDATEC packages/overlays may be missing |
| 6 | Touches register | `sudo apt install -y evtest` then `sudo evtest /dev/input/event5`; tap and drag, Ctrl+C to stop | Lines with `ABS_MT_POSITION_X`, `ABS_MT_POSITION_Y` and `BTN_TOUCH` scroll by while touching, nothing when idle | No events: wrong `eventN`, or a cable or controller fault |
| 7 | EDATEC factory test is off | `systemctl is-enabled touch-test.service; systemctl is-active touch-test.service` | `disabled` / `inactive` | `sudo systemctl disable --now touch-test.service`; it would compete with `HPC_LinuxGUI` for the screen |

If you have no internet for `evtest`, this works for check 6. It prints raw
bytes while you touch, and nothing otherwise:

```bash
sudo timeout 10 cat /dev/input/event5 | xxd | head
```

Harmless output you can ignore:
- `imx219` errors in `dmesg`;
- Bluetooth timeouts;
- `mmc1: Failed to initialize a non-removable card`;
- "terminal is not fully functional" from `systemctl`. That is your SSH
  client's `TERM`; fix it with `export TERM=xterm-256color` or use `--no-pager`.

`/opt/ed-touchscreen-test/ed-touch-test` is EDATEC's factory test program, run
by `touch-test.service`. The package has no command-line tool for us.

### 1.5 Prepare the image for cloning ⏳

#### Pre-checks ✅

| Check | Command | Expected (first build) |
| --- | --- | --- |
| SSH keys will regenerate on clones | `systemctl --no-pager cat regenerate_ssh_host_keys.service` | Unit exists (from `raspberrypi-sys-mods`), `Before=ssh.service`, runs `/usr/lib/raspberrypi-sys-mods/regenerate_ssh_host_keys` |
| Boot time baseline | `systemd-analyze; systemd-analyze blame --no-pager \| head` | `27.8s` total; `ed-lte-daemon.service` alone is `20.0s`; `NetworkManager-wait-online` `6.2s` |
| EDATEC services | `systemctl --no-pager list-unit-files 'ed-*' '*lte*' '*qmi*'` | `ed-lte-daemon` enabled, `ed-net-monitor` disabled, `ed-usb-tools` enabled |
| Free space | `df -h /` | 29G, 2.3G used |

Do **not** delete the SSH host keys unless the regeneration unit exists.
Without keys `ssh.service` fails, and the cloned HMIs are unreachable over the
network.

#### Boot-time decisions baked into the image ✅

- **`ed-lte-daemon.service`** waits for the optional cellular modem and adds
  about 20 s to every boot (also seen on the E180, see `dev_test/readme.md`).
  Disable it in the golden image. On a unit that does use LTE, run
  `sudo systemctl enable ed-lte-daemon.service`.
  ```bash
  sudo systemctl disable ed-lte-daemon.service && sudo reboot
  systemd-analyze        # after reboot
  ```
  Expected: `14.1s` total, `multi-user.target reached after 3.7s in userspace`
  (was 27.8 s / 23.5 s). The remaining top item, `NetworkManager-wait-online`
  (6.2 s), does not delay `multi-user.target`, and provisioning masks it.
- `NetworkManager-wait-online.service` (6 s) is left alone here, because
  `stock-hmi.py` masks it during provisioning.

#### Cleanup

Remove anything unique to this unit so every flashed HMI is distinct:

```bash
# on the HMI, as the last thing before capture
sudo apt clean
sudo rm -f /etc/ssh/ssh_host_*
sudo systemctl enable regenerate_ssh_host_keys.service   # Pi OS regenerates keys on next boot
sudo truncate -s 0 /etc/machine-id                       # regenerated on next boot
sudo rm -f /var/lib/NetworkManager/*.lease
rm -f ~/.bash_history ~/kernel-change.sh
sudo poweroff
```

### 1.6 Capture and shrink ⏳

1. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop-used-in-11-and-15)).
   Do not mount its partitions.
2. Copy the whole disk (it's 29.1 GiB, so check free space):
   ```bash
   sudo dd if=/dev/sdX of=hpc-golden-bookworm-6.6.31.img bs=4M status=progress conv=fsync
   ```
3. Shrink and compress it with [PiShrink](https://github.com/Drewsif/PiShrink).
   PiShrink also arranges for the filesystem to re-expand on first boot.
   ```bash
   sudo pishrink.sh -Z hpc-golden-bookworm-6.6.31.img    # → .img.xz
   sha256sum hpc-golden-bookworm-6.6.31.img.xz > hpc-golden-bookworm-6.6.31.img.xz.sha256
   ```
4. Record in the image's notes:
   - the Pi OS release (2026-10-06);
   - the EDATEC package versions (`dpkg -l | grep ed-`);
   - the kernel (`6.6.31-rpi-v8`);
   - the temporary user name.

### 1.7 Flash the golden image onto an HMI ⏳

Done by the technician, offline.

1. Check the image:
   ```bash
   sha256sum -c hpc-golden-bookworm-6.6.31.img.xz.sha256
   ```
2. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop-used-in-11-and-15)).
   The loader folder comes from the USB.
3. `sudo rpi-imager` → **Use custom** → the golden `.img.xz` → the `RPi-MSD- 0001`
   disk → Write. No customisation is needed, because the image already has `pi`
   and SSH. Alternatively:
   ```bash
   xzcat hpc-golden-bookworm-6.6.31.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
   ```
4. Exit `rpiboot`, unplug the Micro USB cable, connect Ethernet, and power on.
   The panel should show the console within about 30 s. First boot expands the
   filesystem.

---

## 2. Provisioning an HMI from the golden image

This installs the HPC software onto a freshly flashed golden image. It is
offline: the technician has a laptop, an Ethernet cable and the provisioning USB.

### 2.1 Provisioning USB contents

Copy the **contents** of `BOOKWORM/` to the top level of the USB, plus the tools:

```text
USB/
├── stock-hmi.py          # or the PyInstaller-built `stock-hmi`, built ON arm64
├── bin/
│   ├── HPC_LinuxGUI
│   ├── assets/
│   ├── settings.txt
│   └── release-manifest.json
├── debs/                 # offline .deb dependencies (iptables, libpaho-mqtt, ...)
├── rpiboot-msd-cm4/      # loader files from section 0
└── hpc-golden-bookworm-6.6.31.img.xz (+ .sha256)
```

Build the bundle from the repo, not from an old stick. The repo is the source of
truth.

### 2.2 Run the provisioner ⏳

The golden image is Lite, so there is no desktop, no USB auto-mount and no
double-click. The technician works over SSH:

```bash
# laptop
nmcli con up hmi-direct
cat /var/lib/NetworkManager/dnsmasq-eno1.leases
ssh pi@192.168.1.<x>

# on the HMI: insert the provisioning USB
lsblk                                   # find it, e.g. sda1
sudo mount /dev/sda1 /mnt
cd /mnt
sudo python3 ./stock-hmi.py             # or: sudo ./stock-hmi
```

What `stock-hmi.py` does:

- installs the offline debs from `debs/`;
- creates user `nwhs` with the standard password hash (groups `sudo`, `video`,
  `input`, …);
- copies `bin/` to `/home/nwhs/hpc-hmi/bin/`, checks it with `ldd`, and gives
  `HPC_LinuxGUI` `cap_net_admin,cap_net_raw`;
- sets hostname `hpc`;
- adds the sudoers rule `nwhs` (full sudo with password, passwordless
  `nmcli`/`ip`);
- adds a udev rule creating `/dev/input/touchscreen`;
- installs `hmi.service` (runs `HPC_LinuxGUI 192.168.0.2`) and
  `hmi-console.service`, autologin on tty1, `multi-user.target`, SSH on;
- locks every regular user except `nwhs` (for example `pi`) and **deletes them
  on the next boot**, including their `/etc/sudoers.d` rules;
- writes `/var/log/hpc-stock-installer.log`, then reboots.

### 2.3 Verify ⏳

- After the reboot, the panel shows the HPC GUI. Touch works.
- `ssh nwhs@<ip>` works. `pi` no longer exists (`getent passwd pi` prints nothing).
- `systemctl status hmi.service` is active.
- Check `/var/log/hpc-stock-installer.log` for errors.

> TODO: document which address a provisioned HMI uses on Ethernet. The app
> configures networking via `nmcli`, and earlier units were reached at
> `192.168.1.2`.

---

## 3. Updating the HMI software

Two steps: the maintainer refreshes the bundle, then the technician applies it.

### 3.1 Maintainer: refresh the bundle (online) ⏳

`--update` updates the **installer bundle on the maintainer's computer**, not an
HMI. It clones
[`hpc-releases`](https://github.com/NyleWaterHeatingSystems/hpc-releases), reads
`LATEST/manifest.json`, checks the HMI binary's SHA-256, and swaps it into
`bin/` atomically. It keeps `settings.txt` and records `release-manifest.json`.

```bash
cd BOOKWORM
./stock-hmi.py --update
cat bin/release-manifest.json      # confirm release_version
```

Commit the refreshed `BOOKWORM/bin/`, then rebuild the USB (2.1).

### 3.2 Technician: apply it to a provisioned HMI ⏳

Re-running the provisioner is the update path. It re-syncs
`/home/nwhs/hpc-hmi/bin/` from the USB with `rsync --delete`, so **any file on
the HMI under that folder that is not on the USB is removed**. It rewrites the
services and reboots.

```bash
ssh nwhs@<ip>
sudo mount /dev/sda1 /mnt && cd /mnt
sudo python3 ./stock-hmi.py         # run with sudo directly: nwhs does not have
                                    # passwordless sudo, so self-elevation would fail
```

Then verify as in 2.3 and check the version in
`/home/nwhs/hpc-hmi/bin/release-manifest.json`.

> Note (from `dev_test/TODO.md`): on a unit whose OS differs from the bundle's
> (e.g. Trixie), `dpkg` may refuse the bundled debs. The golden image avoids this
> by fixing the OS. An experimental `--patch` mode for post-install OS changes
> such as logrotate is in `dev_test/stock-hmi2.py`.
