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

#### Normal method: the HPC port (eth2) at 192.168.0.4 ✅

The golden image (from 1.5 onward) and every provisioned HMI have a fixed
address on the **HPC controller port, eth2: `192.168.0.4/24`**. The controller
itself is `192.168.0.2`. Plug the laptop into that socket, give the laptop
`192.168.0.100/24`, and SSH in. No DHCP or internet is needed, and any OS works.

```bash
nmcli con add type ethernet ifname eno1 con-name hmi-eth2 \
  ipv4.method manual ipv4.addresses 192.168.0.100/24 ipv6.method link-local
nmcli con up hmi-eth2
ssh pi@192.168.0.4          # before provisioning
ssh nwhs@192.168.0.4        # after provisioning
```

- Never give the laptop `.4` (the HMI) or `.2` (the controller).
- In the field, unplug the controller cable from eth2 (or put a small switch
  between them) while the laptop is connected.
- **Development PCs on a `192.168.0.x` Wi-Fi network** (the first build's PC was,
  with its router at `.1`): the PC already sends all of `192.168.0.x` to Wi-Fi.
  Send only the HMI's address down the cable with a host route, and Wi-Fi keeps
  working:
  ```bash
  nmcli con modify hmi-eth2 ipv4.addresses 192.168.0.100/32 ipv4.routes "192.168.0.4/32"
  nmcli con up hmi-eth2
  ```
  This is why the HMI moved off `.1`: a route for `.1` would also capture the
  router.
- The eth2 socket is the one on USB path `usb-0:3`. See the label table in 1.5.

#### Fallback: laptop as DHCP server (any port, or an HMI without the eth2 profile)

A fresh stock image asks for an address by DHCP on every port. On a direct
cable nothing answers unless the laptop does. A NetworkManager **shared**
profile makes the laptop the DHCP server. It does **not** need internet. During
the golden-image build (1.3) this also gives the HMI the laptop's internet.

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
5. `rpiboot` exits by itself once it has sent the loader. That's normal: the
   eMMC stays exposed until the HMI is powered off, so there's nothing to stop
   afterwards.

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

Power off the HMI, **unplug the Micro USB cable** (or the HMI re-enters USB-boot),
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

### 1.5 Prepare the image for cloning ✅

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
#### Fixed address on the HPC port (eth2) ✅

eth2 gets `192.168.0.4/24` in the golden image. A technician can then SSH in
right after flashing, before provisioning. The bridged ports (eth0, eth1) stay on
DHCP here; the HMI program configures them at runtime.

There is **one definition**,
[`BOOKWORM/network/eth2-hpc.nmconnection`](BOOKWORM/network/eth2-hpc.nmconnection).
It is installed by hand here, and `stock-hmi.py` installs it again on every
provision or update.

**How it fits with `HPC_LinuxGUI`:** every time the HMI program starts, it
deletes and recreates its own `eth2-hpc` profile
(`HPC_Firmware/LinuxHMI/HPC_LinuxGUI/src/system/network_config_nmcli.cpp`),
along with the `br0` bridge over eth0/eth1. Our profile uses the **same name
and address**, so the app replaces it rather than competing with it. eth2 is
`192.168.0.4` whether or not the app has run.

- The address moved from `.1` to `.4` on 2026-10-22 (`HPC_Firmware` branch
  `eth2-static-192.168.0.4`). Until an `HPC_LinuxGUI` build with that change is
  released, a provisioned HMI switches eth2 back to `.1` when the app starts.
- The controller still uses `192.168.0.1` as its **gateway**
  (`HPC_Firmware/iot/src/ethernet_vars.h`). Anything the controller routes
  through the HMI needs that changed to `.4`.
- The app selects the port by name (`ifname eth2`). If the two USB NICs ever
  enumerate in the other order, its address and the bridge land on the wrong
  sockets. Matching by `ID_PATH` (as below) avoids that.

Why it matches by hardware path, not by the name `eth2` or a MAC address:

| Name (first build) | Hardware | `ID_PATH` | Role |
| --- | --- | --- | --- |
| eth0 | CM4 built-in, `bcmgenet` | `platform-fd580000.ethernet` | bridge |
| eth1 | Realtek RTL8153 USB, `r8152` | `platform-fd500000.pcie-pci-0000:01:00.0-usb-0:2:1.0` | bridge |
| **eth2** | Realtek RTL8153 USB, `r8152` | `platform-fd500000.pcie-pci-0000:01:00.0-usb-0:3:1.0` | **HPC controller, 192.168.0.4** |

eth1 and eth2 are two USB network chips, so their names follow USB enumeration
order and could swap between boots. MAC addresses differ per unit. The
`ID_PATH` is the same on every HMI2220-070C.

> ⏳ Record which labelled socket on the case is `usb-0:3` (eth2), for
> technicians.

Collect the table above with:

```bash
for i in /sys/class/net/eth*; do echo "== ${i##*/} mac=$(cat $i/address)"; udevadm info -q property -p $i | grep -E '^(ID_PATH|ID_NET_DRIVER|ID_BUS|ID_MODEL|ID_VENDOR)='; done
ip -br link        # the port with a cable shows UP / LOWER_UP
```

Install it on the HMI, while still connected through the DHCP fallback:

```bash
# laptop, from the repo
scp BOOKWORM/network/eth2-hpc.nmconnection pi@192.168.1.<x>:     # note the trailing ':'
# HMI
sudo install -m 600 -o root -g root ~/eth2-hpc.nmconnection /etc/NetworkManager/system-connections/
rm ~/eth2-hpc.nmconnection
sudo nmcli con reload
sudo reboot
```

Reconnect on `192.168.0.4` ([normal method](#normal-method-the-hpc-port-eth2-at-19216804-)),
then verify:

| Check | Command | Expected (first build) |
| --- | --- | --- |
| Profile active on eth2 | `nmcli -f NAME,DEVICE con show --active` | `eth2-hpc  eth2` |
| Address | `ip -br addr show eth2` | `eth2 UP 192.168.0.4/24 fe80::…/64` |
| Right socket | `udevadm info -q property -p /sys/class/net/eth2 \| grep ID_PATH` | `…-usb-0:3:1.0` |

If the profile is not active, check that the file is mode `600` and owned by
root (NetworkManager ignores it otherwise), and that `ID_PATH` matches the
`[match] path=` line.

#### Cleanup ✅

Remove anything unique to this unit so every flashed HMI is distinct. This must
be the **last** thing done before capture. **Do not boot the HMI again before
1.6**: booting would recreate the keys and machine ID.

`regenerate_ssh_host_keys` (checked on the first build) deletes the keys, runs
`ssh-keygen -A`, then disables itself. So it runs exactly once, on each clone's
first boot. The keys are also removed here so that no private key ends up in the
image file.

```bash
# on the HMI
sudo apt clean
sudo systemctl enable regenerate_ssh_host_keys.service
sudo rm -f /etc/ssh/ssh_host_*
sudo truncate -s 0 /etc/machine-id                       # systemd creates a new one on first boot
ls -l /var/lib/dbus/machine-id                           # should be a symlink -> /etc/machine-id
sudo rm -f /var/lib/NetworkManager/*.lease
rm -f ~/kernel-change.sh
```

Verify, then power off without leaving shell history behind:

```bash
systemctl is-enabled regenerate_ssh_host_keys.service   # enabled
ls /etc/ssh/ssh_host_* 2>&1                             # No such file or directory
wc -c < /etc/machine-id                                 # 0
systemctl is-enabled ed-lte-daemon.service              # disabled
ls -l /etc/NetworkManager/system-connections/           # only eth2-hpc.nmconnection, -rw------- root root
ls -l /boot/firmware/userconf.txt                       # No such file (it holds a password hash)

unset HISTFILE; rm -f ~/.bash_history; sudo poweroff
```

### 1.6 Capture and shrink ✅

The image file is named after the build date: `hpc-golden-YYYY-MM-DD.img`. The
first build is `hpc-golden-2026-10-22.img`.

1. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop-used-in-11-and-15)).
   The desktop may auto-mount `bootfs`. Unmount it, and do not mount anything else:
   ```bash
   udisksctl unmount -b /dev/sdX1
   lsblk /dev/sdX          # MOUNTPOINTS column empty
   ```
2. Copy the whole disk. It's 29.1 GiB, so check free space first. **`if=` is the
   eMMC and `of=` is the file**; reversing them overwrites the eMMC.
   ```bash
   sudo dd if=/dev/sdX of=hpc-golden-2026-10-22.img bs=4M status=progress conv=fsync
   sudo chown $USER: hpc-golden-2026-10-22.img
   ```
3. Shrink and compress it with [PiShrink](https://github.com/Drewsif/PiShrink)
   (Arch: `yay -S pishrink-git`, command `pishrink.sh`). `-Z` compresses with
   xz, and `-a` uses all CPU cores.
   ```bash
   sudo pishrink.sh -Z -a hpc-golden-2026-10-22.img    # → .img.xz, replaces the .img
   sha256sum hpc-golden-2026-10-22.img.xz > hpc-golden-2026-10-22.img.xz.sha256
   ls -lh hpc-golden-2026-10-22.img*
   ```
   Observed on the first build (PiShrink v26.03.16):
   ```
   pishrink.sh: An existing /etc/rc.local was not found, autoexpand may fail...
   Creating new /etc/rc.local
   rootfs: 64723/1810016 files (0.2% non-contiguous), 679388/7500800 blocks
   Resizing the filesystem on /dev/loop0 to 825439 (4k) blocks.
   pishrink.sh: Zeroed 950M
   pishrink.sh: Shrunk hpc-golden-2026-10-22.img.xz from 30G to 507M in 1m 30s
   ```
   - The `rc.local` warning is expected on Bookworm, which ships without one.
     PiShrink writes its own `/etc/rc.local` to expand the filesystem on first
     boot; whether it does so is checked in 1.7.
   - `fsck` errors at the "Checking filesystem" step mean the copy is bad: redo
     step 2.
4. First-build result:

   | File | Size | SHA-256 |
   | --- | --- | --- |
   | `hpc-golden-2026-10-22.img.xz` | 507M | `dcf8cf1403c065be78ce5aad20b8625a58395161cd887240d99ba2af0d2e0020` |

5. Record in the image's notes:
   - Pi OS release: `2026-10-06-raspios-bookworm-arm64-lite` ✅
   - kernel: `6.6.31-rpi-v8` (EDATEC `ed-linux-image-6.6.31-v8`, held) ✅
   - temporary user: `pi` (password in the team password store) ✅
   - EDATEC packages (`dpkg -l 'ed-*'`, read on the first flashed HMI) ✅:

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

### 1.7 Flash the golden image onto an HMI ✅

Done by the technician, offline.

1. Check the image:
   ```bash
   sha256sum -c hpc-golden-2026-10-22.img.xz.sha256
   ```
2. Expose the eMMC ([procedure above](#procedure-expose-the-emmc-on-the-laptop-used-in-11-and-15)).
   The loader folder comes from the USB.
3. `sudo rpi-imager` → **Use custom** → the golden `.img.xz` → the `RPi-MSD- 0001`
   disk → Write. No customisation is needed, because the image already has `pi`
   and SSH. Alternatively:
   ```bash
   xzcat hpc-golden-2026-10-22.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
   ```
   The progress line jumps to ~3.9 GB within seconds, then appears to hang with
   no prompt. That's expected: the data went into the laptop's write cache, and
   `conv=fsync` waits while it drains to the eMMC at only about 5 MB/s, which
   takes roughly 10 minutes. Watch it drain with
   `watch -n5 grep -e Dirty -e Writeback: /proc/meminfo`. Don't unplug until
   the prompt returns. Observed on the first flash:
   ```
   0+118057 records in
   0+118057 records out
   3926258176 bytes (3.9 GB, 3.7 GiB) copied, 743.663 s, 5.3 MB/s
   ```
   The byte count must be `3926258176` for this image. `0+N records` is normal
   when reading from a pipe: every read was a partial block, and dd writes
   exactly what it reads.
4. Power off the HMI, unplug the Micro USB cable, connect Ethernet, and power on.
   The panel should show the console within about 30 s. First boot expands the
   filesystem.
5. Verify from the laptop on the eth2 socket ([normal method](#normal-method-the-hpc-port-eth2-at-19216804)) ✅:

   | Check | Command | Expected (first flash) |
   | --- | --- | --- |
   | Reachable, new host key | `ssh-keygen -R 192.168.0.4; ssh pi@192.168.0.4` | `The authenticity of host '192.168.0.4' can't be established. ED25519 key fingerprint is …` (new key), then logs in as `pi@raspberrypi` |
   | Filesystem expanded | `df -h /` | `/dev/mmcblk0p2   29G  2.1G   25G   8% /` |
   | Unique machine ID | `cat /etc/machine-id` | 32 hex chars, new on each HMI (first flash: `fca65ad5…3517`) |
   | Kernel | `uname -r` | `6.6.31-rpi-v8` |
   | Display | `cat /proc/fb` | `0 vc4drmfb` |
   | eth2 profile | `nmcli -f NAME,DEVICE con show --active` | `eth2-hpc  eth2` and `lo  lo` |
   | EDATEC versions for 1.6 notes | `dpkg -l 'ed-*'` | 9 packages, all `ii`; versions in 1.6 step 5 |

   If `df` still shows ~3G, PiShrink's `/etc/rc.local` didn't run; expand by
   hand with `sudo raspi-config nonint do_expand_rootfs && sudo reboot`.

---

## 2. Provisioning an HMI from the golden image

This installs the HPC software onto a freshly flashed golden image. It is
offline: the technician has a laptop, an Ethernet cable and the provisioning USB.

### 2.1 Build the provisioning USB ⏳

On the maintainer's PC, with `stock_hmi` and `hpc-releases` checked out side by
side. Use a FAT32 or exFAT stick, and don't build from an old stick: the repos
are the source of truth.

```bash
cd stock_hmi
./make-usb-kit.py /run/media/$USER/<USB>              # release named in hpc-releases/CURRENT
./make-usb-kit.py /run/media/$USER/<USB> --release v2.0.8 --replace   # a specific release
udisksctl unmount -b /dev/sdX1
```

It checks the HMI binary against the release manifest's SHA-256 before copying,
and prints what went into the kit. Observed when tested into a folder:

```
built:     2026-10-23T16:02:42Z
app:       v2.0.8 (hmi_v2.0.8.bin)
stock_hmi: 283621e-dirty
releases:  a808bf7
```

`-dirty` means the `stock_hmi` checkout had uncommitted changes. Build release
kits from a clean, committed checkout. The kit:

```text
USB/
├── stock-hmi.py
├── bin/          # HPC_LinuxGUI, assets/, release-manifest.json
├── debs/         # offline .deb dependencies (iptables, libpaho-mqtt, ...)
├── network/      # eth2-hpc.nmconnection: eth2 = 192.168.0.4, re-applied on every run
├── KIT.txt       # the versions above
└── SHA256SUMS    # one line per file (331 for v2.0.8)
```

The golden image and the `rpiboot-msd-cm4/` loader folder are only needed for
flashing (1.7). Copy them to the stick by hand if the technician will flash too.

### 2.2 Run the provisioner ⏳

The golden image is Lite, so there is no desktop, no USB auto-mount and no
double-click. The technician works over SSH:

```bash
# laptop: cable in the HMI's eth2 socket
nmcli con up hmi-eth2               # laptop = 192.168.0.100/24
ssh pi@192.168.0.4

# on the HMI: the provisioner needs these; any MISSING stops it partway.
# On the 2026-10-22 golden image every one is present (/usr/bin/rsync, /usr/sbin/setcap, ...).
for c in rsync setcap ldd visudo nmcli udevadm hostnamectl python3; do printf '%-12s %s\n' $c "$(command -v $c || echo MISSING)"; done

# on the HMI: insert the provisioning USB
lsblk                                   # find it, e.g. sda1
sudo mount /dev/sda1 /mnt
cd /mnt
cat KIT.txt                             # the release you expect?
sha256sum -c --quiet SHA256SUMS && echo KIT OK   # silent per-file, then KIT OK
sudo python3 ./stock-hmi.py             # or: sudo ./stock-hmi
```

What `stock-hmi.py` does:

- installs the offline debs from `debs/`;
- creates user `nwhs` with the standard password hash (groups `sudo`, `video`,
  `input`, …);
- copies `bin/` to `/home/nwhs/hpc-hmi/bin/`, checks it with `ldd`, and gives
  `HPC_LinuxGUI` `cap_net_admin,cap_net_raw`;
- sets hostname `hpc`;
- installs `network/eth2-hpc.nmconnection` (eth2 = `192.168.0.4/24`) again, so
  the HPC port is restored even if something changed it;
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
- `ssh nwhs@192.168.0.4` works. `pi` no longer exists (`getent passwd pi`
  prints nothing).
- `nmcli -f NAME,DEVICE con show --active` shows `eth2-hpc  eth2`.
- `systemctl status hmi.service` is active.
- Check `/var/log/hpc-stock-installer.log` for errors.

> Answered: the HMI program does recreate `eth2-hpc` on every start, with the
> same name and (from `HPC_Firmware` branch `eth2-static-192.168.0.4`) the same
> address. See 1.5.

---

## 3. Updating the HMI software

Two steps: the maintainer builds a kit, then the technician applies it.

### 3.1 Maintainer: build a kit with the new release ⏳

Publish the release to `hpc-releases` (see its README), pull it, then build a
fresh kit as in 2.1. There is no separate update command: the kit always takes
the app straight from `hpc-releases`.

### 3.2 Technician: apply it to a provisioned HMI ⏳

Re-running the provisioner is the update path. It re-syncs
`/home/nwhs/hpc-hmi/bin/` from the USB with `rsync --delete`, so **any file on
the HMI under that folder that is not on the USB is removed**. The one exception
is `bin/settings.txt`: the app creates it on first run, it holds this unit's
configuration, and the provisioner never replaces or deletes it (⏳ not yet
verified on hardware). It rewrites the
services and reboots.

```bash
ssh nwhs@192.168.0.4                # laptop on eth2 as 192.168.0.100/24
sudo mount /dev/sda1 /mnt && cd /mnt
cat KIT.txt; sha256sum -c --quiet SHA256SUMS && echo KIT OK
sudo python3 ./stock-hmi.py         # run with sudo directly: nwhs does not have
                                    # passwordless sudo, so self-elevation would fail
```

Then verify as in 2.3 and check the version in
`/home/nwhs/hpc-hmi/bin/release-manifest.json`.

> Note (from `dev_test/TODO.md`): on a unit whose OS differs from the bundle's
> (e.g. Trixie), `dpkg` may refuse the bundled debs. The golden image avoids this
> by fixing the OS. An experimental `--patch` mode for post-install OS changes
> such as logrotate is in `dev_test/stock-hmi2.py`.
