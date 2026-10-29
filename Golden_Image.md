# Create a preconfigured image without NYLE SYSTEMS Software installed.

- **Objective 1:** Configure a more perfect starting OS Image.
- **Objective 2:** Get OEM to ship hmis with this image.
- **Compatability:** ED-HMI222-070c. ED-HMI212-070c — see service patch (Bottom).

## Golden_Image creation, and change log from default PiOS

- **Image Birth:** 10,28,2026
- **Starting image:** `2026-10-06-raspios-trixie-arm64.img`

### RAW GOLDEN.img, Compressed, archived Checksums

```text
71a36a7a24529c2d7db39bac8f381bd1b6155349e021e00db1358f6d136a8300  GOLDEN.img
77c6411867850938392d0132b33b83b19f9d034eeb1abd714956b5c3c029e4be  GOLDEN_shrunk.img
b66a9ff13403acfd58d0c329fe3c02f6251566945ce871b8825e87a7dd7d1c8e  GOLDEN_shrunk.img.xz
```
**Image sizes:**
```bash
~/Desktop/GOLDEN$ ls -alh
-rw-r--r--  1 eri eri  30G Oct 29 10:40 GOLDEN.img
-rw-r--r--  1 eri eri 8.5G Oct 29 10:45 GOLDEN_shrunk.img
-rw-r--r--  1 eri eri 1.2G Oct 29 10:45 GOLDEN_shrunk.img.xz
```
**OS file Verification:**
```verify
cd /
find . -path './home/pi' -prune -o -printf '%y %p\n' | LC_ALL=C sort > /tmp/tree.txt
sha256sum /tmp/tree.txt
f2921b07661a7a4366d789fa19c44c281a3e71a67bf231c35afd5401e1de7a08  /tmp/tree.txt
```
**there might be better methods**  
[-] wouldnt catch files replaced with files of the same name.  
[+] catch missing, or additional files.  
[+] A diff on tree.txt would tell you which files.  
[+] runs fast.   
[+] could be run in the future. .. (post install with some adjustments.)  

## About 

**Kernel**
```console
pi@raspberrypi:~ $ uname -a
Linux raspberrypi 6.18.50+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.18.50-1+rpt1 (2026-09-11) aarch64
```

- **Boot time:** 13s
- **Space freed:** ~2GB

## Preconfigured

- **ssh**
- **User:** `pi`
- **Pass:** `raspberry`

## Created Files

### `/etc/logroate.d/hpc`

```conf
/var/log/hpc/data/*/*/*.csv {
    daily
    maxsize 100M
    # keep 20 years of logs before a delete
    rotate 7300
    compress
    nodelaycompress
    missingok
    notifempty
    copytruncate
}
```

## Edited

### Changed `/boot/firmware/config.txt`

```ini
[all]
dtoverlay=vc4-kms-dsi-edatec-panel-070c,interrupt=7
dtoverlay=uart4
dtoverlay=uart5
```

### Changed `/boot/firmware/cmdline.txt`

```text
console=serial0,115200 console=tty3 root=PARTUUID=1808c7b9-02 rootfstype=ext4 fsck.repair=yes rootwait quiet plymouth.ignore-serial-consoles
```

## Moved files

```bash
sudo rsync -crt /usr/lib/linux-image-6.18.50+rpt-rpi-v8/broadcom/bcm27*.dtb /boot/firmware/
sudo rsync -crt /usr/lib/linux-image-6.18.50+rpt-rpi-v8/overlays/*.dtb* \
    /usr/lib/linux-image-6.18.50+rpt-rpi-v8/overlays/README \
    /boot/firmware/overlays/

sudo cp -v /boot/vmlinuz-6.18.50+rpt-rpi-v8 /boot/firmware/kernel8.img
sudo cp -v /boot/initrd.img-6.18.50+rpt-rpi-v8 /boot/firmware/initramfs8
sudo rm -f /boot/firmware/.firmware_revision
sudo sed -i '/^KERNEL=/d; /^INITRAMFS=/d' /etc/default/raspi-firmware

printf '%s\n' \
    'KERNEL=6.18.50+rpt-rpi-v8' \
    'INITRAMFS=6.18.50+rpt-rpi-v8' |
    sudo tee -a /etc/default/raspi-firmware
```

## Removed packages

`geany`, `thony`, `sane`, `cups`, `rpi-connect`, `firefox`, `rpi-imager`, `bluez`, `chromium`, `chromium-l10n`, `rpi-chromium-mods`

```console
$ sudo apt autoremove
REMOVING:
  docutils-common     python3-docutils         python3-psutil
  geany-common        python3-html5lib         python3-roman
  libadwaita-1-0      python3-isort            python3-send2trash
  libevent-2.1-7t64   python3-jedi             python3-soupsieve
  mypy                python3-logilab-common   python3-tomlkit
  pipewire-libcamera  python3-lxml             python3-webencodings
  pylint              python3-mccabe           update-inetd
  python3-astroid     python3-mypy             xsel
  python3-asttokens   python3-mypy-extensions  zenity
  python3-bs4         python3-orjson           zenity-common
  python3-cssselect   python3-parso
  python3-dill        python3-platformdirs
```

## Removed Files / Folders

```console
:~ $ rm -rf Downloads/ Music/ Videos/ Documents/ Pictures/ Templates/ Public/
```

## Installed Packages

```bash
sudo apt install iptables libpaho-mqtt libpaho-mqtt-dev libx11-dev iptables libip6tc-dev
```

## OTHER CONFIG

### Disable Autoupdates

```console
$ sudo tee /etc/apt/apt.conf.d/99disable-auto-updates >/dev/null <<'EOF'
APT::Periodic::Enable "0";
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::Unattended-Upgrade "0";
EOF
```

```bash
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
sudo systemctl mask apt-daily.service apt-daily-upgrade.service
```

### Disable NetworkMangager-wait-online service

```bash
sudo systemctl disable --now NetworkManager-wait-online.service
```

### Configure Passwordless sudo

```bash
printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$(id -un)" | sudo tee /etc/sudoers.d/010_pi-nopasswd >/dev/null
sudo chmod 0440 /etc/sudoers.d/010_pi-nopasswd
sudo visudo -c
```

### Add udev rule for auto enable ext4 automount

addfile `/etc/udev/rules.d/99-hmi-usb-automount.rules`

```udev
SUBSYSTEM=="block", SUBSYSTEMS=="usb", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_FS_TYPE}=="ext4", ENV{UDISKS_AUTO}="1"
```

```bash
sudo udevadm control --reload-rules
```

### Add a service to auto mount USB devices

```bash
mkdir -p ~/.local/bin ~/.config/autostart

cat > ~/.local/bin/hmi-usb-open.py <<'PY'
import fcntl
import os
import subprocess
from gi.repository import Gio, GLib

# Prevent duplicate watchers.
lock = open(os.path.join(os.environ["XDG_RUNTIME_DIR"],
                         "hmi-usb-open.lock"), "w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(0)

def mounted(monitor, mount):
    volume = mount.get_volume()
    if volume is None:
        return
    device = volume.get_identifier("unix-device")
    folder = mount.get_root().get_path()
    if not device or not folder:
        return
    result = subprocess.run(
        ["udevadm", "info", "--query=property", "--name", device],
        capture_output=True, text=True
    )
    if "ID_BUS=usb" in result.stdout.splitlines():
        subprocess.Popen(["pcmanfm", folder])

monitor = Gio.VolumeMonitor.get()
monitor.connect("mount-added", mounted)
GLib.MainLoop().run()
PY

cat > ~/.config/autostart/hmi-usb-open.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Open mounted USB folders
Exec=/usr/bin/python3 $HOME/.local/bin/hmi-usb-open.py
Terminal=false
EOF
```

### Disable auto-login tty1

```console
$ sudo mv /etc/systemd/system/getty@tty1.service.d/autologin.conf /etc/systemd/system/getty@tty1.service.d/autologin.conf.disabled
$ sudo systemctl daemon-reload
$ sudo systemctl restart getty@tty1.service
```

### HOLD ALL Packages

apt isn't disabled, but updating installed pkgs with apt is.

This applies to kernels as well. doesnt effect dpkg

```bash
dpkg-query -W -f='${db:Status-Status} ${binary:Package}\n' |
    awk '$1 == "installed" {print $2}' |
    xargs -r sudo apt-mark hold
```

### Undo All pkg holds

```bash
apt-mark showhold | xargs -r sudo apt-mark unhold
```

## ED-HMI2120-070C requires patching display bridge

### Test Fix Ed-HMI2120-070C (temporary)

```bash
sudo i2ctransfer -f -y 10 w2@0x27 0x11 0x01
```

```bash
sudo tee /etc/systemd/system/ed-hmi-display-fix.service >/dev/null <<'EOF'
[Unit]
Description=Apply ED-HMI display register workaround
After=display-manager.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart=/usr/sbin/i2ctransfer -f -y 10 w2@0x27 0x11 0x01
RemainAfterExit=yes
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ed-hmi-display-fix.service
```
