# Nyle Systems: Golden Image

- an extra light, desktop os for quick provissioning.
- auto mounts USB disks.
- quiet boot no splash screen.
- precofigured log rotation.
- preinstalled depenedencies.
- expands FS on first boot.
- ssh preconfigured
- desktop autologin
- stripped down / bare neccesities.
- easy config with provissioning tool from this repo.

# Checksums:
**archive, decompressed hashes:**
```checksum
b66a9ff13403acfd58d0c329fe3c02f6251566945ce871b8825e87a7dd7d1c8e  GOLDEN_shrunk.img.xz
77c6411867850938392d0132b33b83b19f9d034eeb1abd714956b5c3c029e4be  GOLDEN_shrunk.img
```
## Golden_Image creation from default PiOS

- **Image Birth:** 10.28.2026
- **Starting image:** `2026-10-06-raspios-trixie-arm64.img`

# Credentials
**User:** pi  
**pass:** raspberry


# Usage:
**Download:** GOLDEN_shrunk.img.xz  
**Check integrity:**
```integrity1
echo 'b66a9ff13403acfd58d0c329fe3c02f6251566945ce871b8825e87a7dd7d1c8e  GOLDEN_shrunk.img.xz' | sha256sum -c -
GOLDEN_shrunk.img.xz: OK
```
**Decompress** GOLDEN_shrunk.img.xz  
**Check extraction integrity:** 
```integrity2
echo '77c6411867850938392d0132b33b83b19f9d034eeb1abd714956b5c3c029e4be  GOLDEN_shrunk.img' | sha256sum -c -
GOLDEN_shrunk.img: OK
```

**Clone to your ED-HMI2220-070c**  
**Warning:** Flashing erases the target drive. Use **lsblk** to identify the HMI;  
replace /dev/sda below if needed.

1. With hmi powered off, plug usb micro into HMI.  
   insert other end into your PC.
2. Prepare to enter bootloader: run **sudo rpiboot**
3. Enter bootloader: power on device.  
   rpiboot will detect HMI and enter program mode.
4. unmount partitions if automounted:  
   **sudo umount /dev/sda1 /dev/sda2**
5. clone image to HMI:
```clone
sudo dd if=GOLDEN_shrunk.img of=/dev/sda bs=16M conv=fsync status=progress
```

# Troubleshooting:
**What a filed checksum looks like**
```hash_fail
$ echo '77c6411867850938392d0132b33b83b19f9d034eeb1abd714956b5c3c029e4be  GOLDEN_shrunk.img' | sha256sum -c -
GOLDEN_shrunk.img: FAILED
sha256sum: WARNING: 1 computed checksum did NOT match
```

**disk enumeration at unexpected loaction**
```wrong
$ sudo umount /dev/sda1 /dev/sda2
umount: /dev/sda1: no mount point specified.
umount: /dev/sda2: umount failed: Invalid argument.
### WEIRD Response right? 
### Your disk might be enumerated at an unexpected location
```

```normal
$ sudo umount /dev/sdb1 /dev/sdb2
$ sudo umount /dev/sdb1 /dev/sdb2
umount: /dev/sdb1: not mounted.
umount: /dev/sdb2: not mounted.
```

























