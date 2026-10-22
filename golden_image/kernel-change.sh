#!/bin/bash

KERNEL_VERSION=$1
FIRMWARE_FILE="/etc/default/raspi-firmware"

function update_raspi-firmware(){
    local key=$1
    local value=$2
    grep -q "^${key}=" $FIRMWARE_FILE
    if [ $? -eq 0 ];then
        sed -i "/^${key}=*/c${key}=${value}" $FIRMWARE_FILE
    else
        sed -i "\$a${key}=${value}" $FIRMWARE_FILE
    fi
}

function handle_kernel_file(){
    local firmware_dst="/boot/firmware"
    local overlay_path="/usr/lib/linux-image-${KERNEL_VERSION}/overlays"
    local dtb_path="/usr/lib/linux-image-${KERNEL_VERSION}/broadcom"
    local flavour="$(echo "$KERNEL_VERSION" | rev | cut -f1 -d- | rev)"
    local kernel_dst="$firmware_dst/kernel$(echo "$flavour" | sed 's/^v//;s/^6//;s/2712/_2712/;').img"
    local image_path="/boot/vmlinuz-${KERNEL_VERSION}"
    local initramfs_dst="$firmware_dst/initramfs$(echo "$flavour" | sed 's/^v//;s/^6//;s/2712/_2712/;')"
    local initramfs_path="/boot/initrd.img-${KERNEL_VERSION}"

    rsync -crt "${dtb_path}"/bcm27*.dtb /boot/firmware/
    rsync -crt "${overlay_path}"/*.dtb* "${overlay_path}"/README "${firmware_dst}/overlays"
    if [ -e "${firmware_dst}/.firmware_revision" ]; then
        echo "WARNING: raspi-firmware: replacing rpi-update kernels" >&2
        rm -f "${firmware_dst}/.firmware_revision"
    fi
    cp -v "$image_path" "$kernel_dst"
    cp -v "$initramfs_path" "$initramfs_dst"
}

function start(){
    if [ -d /usr/lib/linux-image-${KERNEL_VERSION} ];then
        if [ -d /lib/modules/${KERNEL_VERSION} ];then
            handle_kernel_file
            update_raspi-firmware "KERNEL" "${KERNEL_VERSION}"
            update_raspi-firmware "INITRAMFS" "${KERNEL_VERSION}"
        fi
    fi
}


start
