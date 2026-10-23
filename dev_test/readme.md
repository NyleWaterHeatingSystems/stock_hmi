> **Note (2026-10-23):** `stock-hmi2.py` is an unmaintained experiment. It
> predates the golden image and `make-usb-kit.py` and has drifted from
> `../stock-hmi.py`. Use `../stock-hmi.py`; port `--patch` into it if that mode
> is still wanted.

# expiramental:

- Update a previously provissioned software with --patch option  

This is to add the logrotate, log compression function, but may include   
other OS updates and system changes, post install.  

stock-hmi.py --patch will report kernel version and OS install version  
for informational purposes, and add the "hpc" config file to /etc/logrotate.d/  

PROVIDED: The user is now nwhs, and the password corrosponds to the encrypted  
password in APP_PASSWORD_HASH


check boot time --done
check spash screen
check log rotation. 
add logrotate to stock-hmi.py (auto install )

investigate labwc touchscreen issues / default screen / session. --Done, wrote to edatec

investigate services.


look at nmcli configs / networking

prevent tty terminal currsor from interupting HPCLinuxGUI interface. 


e180 has a boottime of ~=30s, with ed-lte-daemon.service (20.047s)
# splash screen:
splash location for alternate splash:
/usr/share/plymouth/themes/pix/splash.png  

does not support animated gif, can script one if neccisary.  

Forgo splash: rm quiet  
nwhs@hpc:~ $ cat /boot/firmware/cmdline.txt   
console=serial0,115200 console=tty1 root=PARTUUID=e3fe0840-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles net.ifnames=0 cfg80211.ieee80211_regdom=CN

# hpcLinuxGUI service:

/etc/systemd/system/hmi.service

[Unit]
Description=HPC framebuffer HMI
#Wants=NetworkManager.service getty@tty1.service hmi-console.service
#After=NetworkManager.service getty@tty1.service hmi-console.service systemd-user-sessions.service
Wants=NetworkManager.service hmi-console.service
After=NetworkManager.service hmi-console.service systemd-user-sessions.service

[Service]
Type=simple
User=nwhs
Group=nwhs
SupplementaryGroups=video render input dialout netdev gpio i2c spi tty
WorkingDirectory=/home/nwhs/hpc-hmi/bin
Environment=HOME=/home/nwhs
Environment="QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/touchscreen"
Environment="TSLIB_TSDEVICE=/dev/input/touchscreen"
Environment="SDL_MOUSEDEV=/dev/input/touchscreen"
# Turn off cursor, and disable blinks
ExecStartPre=+/bin/sh -c '/usr/bin/setterm --term linux --clear all --cursor off < /dev/tty1 > /dev/tty1'
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'
ExecStart=/home/nwhs/hpc-hmi/bin/HPC_LinuxGUI 192.168.0.2
Restart=always
RestartSec=2
StandardInput=null
StandardOutput=journal
StandardError=journal


[Install]
WantedBy=multi-user.target



# verify log rotation ( compression )
- sudo mkdir -p /var/log/hpc/date/10/20/ # make a directory as one does not exist (im on the panel unit)
- nwhs@hpc:/var/log/hpc/data/10/20 $ sudo cp /home/nwhs/2026-10-06_16-31-11.csv . # put a log to operate on in place
- $ systemctl list-timers --all logrotate.timer  # verify timers
    NEXT                        LEFT          LAST                        PASSED       UNIT            ACTIVATES        
    Wed 2026-04-22 00:00:00 BST 3h 38min left Tue 2026-04-21 17:42:59 BST 2h 38min ago logrotate.timer logrotate.service

    1 timers listed.
- sudo logrotate --verbose --force /etc/logrotate.d/hpc # force a rotation
-  # check the rotation :
<pre>
nwhs@hpc:/var/log/hpc/data/10/20 $ ls -al
total 148
drwxr-xr-x 2 root root   4096 Apr 21 20:36 .
drwxr-xr-x 3 root root   4096 Apr 21 20:34 ..
-rw-r--r-- 1 root root      0 Apr 21 20:36 2026-10-06_16-31-11.csv
-rw-r--r-- 1 root root 140310 Apr 21 20:35 2026-10-06_16-31-11.csv.1.gz

# note file is retatined, but 0 bytes data compressed
</pre>

- verify compression: # im just do it manualy:
--> copy gz file to log src, extact & compare
eri@sys76:~/Desktop/hmi_hpc+LOGS/hpc_logs/10$ diff 2026-10-06_16-31-11.csv A2026-10-06_16-31-11.csv 
--No DIFF

# prevent cellular from holding up boot:
sudo systemctl disable ed-lte-daemon.service

--> start it when wanted:
sudo systemctl enable ed-lte-daemon.service


# NEVER SEEN THIS BS BEFORE::

nwhs@hpc:~ $ sudo shutdown -h now
[sudo] password for nwhs: 

Broadcast message from root@hpc on pts/1 (Tue 2026-04-21 21:14:35 BST):

The system will power off now!

Call to PowerOff failed: Connection timed out <--WAT
Connection to 192.168.1.2 closed by remote host.
Connection to 192.168.1.2 closed.
---> it did shutdow, but it threw this error Ive never seen.

