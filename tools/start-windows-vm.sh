#!/usr/bin/env bash
# Boot the Windows install on this machine's own disk inside QEMU, pass the
# scanner through, and record all of its USB traffic. This is how the Canon
# Windows driver's behaviour was captured; see docs/FINDINGS.md.
#
# The physical disk is only ever read. QEMU opens it read-only as the backing
# image of a qcow2 overlay, so every write Windows makes lands in the overlay
# file in VM_DIR, never on the disk. The user also only gets a read ACL on the
# disk, so a write could not reach it anyway. Do not run this while Windows is
# hibernated and you plan to boot it natively afterwards with pending changes.
#
# Setup, once per boot (the ACL disappears on reboot):
#   sudo setfacl -m u:$USER:r /dev/nvme0n1
# Then copy the Windows boot files once:
#   tools/copy-windows-boot.py --disk /dev/nvme0n1 --dest "$VM_DIR/esp-copy"
#
# Environment: DISK (default /dev/nvme0n1), VM_DIR (default ~/vm/windows-scanner),
# USB_ID (default 04a9:1904, the LiDE 100).
set -euo pipefail

disk=${DISK:-/dev/nvme0n1}
vm=${VM_DIR:-$HOME/vm/windows-scanner}
usb=${USB_ID:-04a9:1904}
overlay="$vm/windows-overlay.qcow2"
vars="$vm/OVMF_VARS_4M.fd"
capture="$vm/captures/usb-$(date +%Y-%m-%d_%H-%M-%S).pcap"

if [[ ! -r $disk ]]; then
    echo "No read access to $disk. Run this once (it lasts until reboot):" >&2
    echo "  sudo setfacl -m u:$USER:r $disk" >&2
    exit 1
fi
if [[ -w $disk ]]; then
    echo "Refusing to start: $disk is writable by $USER, and this VM must only read it." >&2
    exit 1
fi
if [[ ! -e $vm/esp-copy/EFI/BOOT/BOOTX64.EFI ]]; then
    echo "Missing $vm/esp-copy; run tools/copy-windows-boot.py first." >&2
    exit 1
fi

mkdir -p "$vm/captures"
[[ -f $vars ]] || cp /usr/share/OVMF/OVMF_VARS_4M.fd "$vars"
[[ -f $overlay ]] || qemu-img create -q -f qcow2 -F raw -b "$disk" "$overlay"
# A plain FAT32 image that Windows sees as a USB stick named LINUXSHARE, for
# getting files out. Read it from Linux only while the VM is off.
[[ -f $vm/transfer.img ]] || mkfs.fat -F 32 -n LINUXSHARE -C "$vm/transfer.img" 1048576 >/dev/null

echo "USB capture: $capture"
# The real EFI partition may boot shim/GRUB first; esp-copy holds the Windows
# boot manager as the fallback loader on a small read-only first boot disk.
exec qemu-system-x86_64 \
    -name "Windows (physical disk read-only)" \
    -enable-kvm -machine q35 -cpu host -smp 4 -m 6G \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file="$vars" \
    -blockdev driver=host_device,node-name=phys,filename="$disk",read-only=on \
    -blockdev driver=file,node-name=overlay-file,filename="$overlay" \
    -blockdev driver=qcow2,node-name=win,file=overlay-file,backing=phys \
    -device nvme,drive=win,serial=WINPHYS01,bootindex=1 \
    -blockdev driver=vvfat,node-name=bootcopy,dir="$vm/esp-copy",read-only=on \
    -device virtio-blk-pci,drive=bootcopy,bootindex=0 \
    -device qemu-xhci,id=xhci \
    -device usb-tablet,bus=xhci.0 \
    -blockdev driver=file,node-name=transfer-file,filename="$vm/transfer.img" \
    -blockdev driver=raw,node-name=transfer,file=transfer-file \
    -device usb-storage,bus=xhci.0,drive=transfer,removable=on \
    -device usb-host,bus=xhci.0,vendorid=0x${usb%%:*},productid=0x${usb##*:},pcap="$capture" \
    -nic none \
    -vga std -display gtk \
    -qmp unix:"$vm/qmp.sock",server=on,wait=off
