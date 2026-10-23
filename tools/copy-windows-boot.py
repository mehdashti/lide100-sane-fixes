#!/usr/bin/env python3
"""Copy the Windows boot manager out of a disk's EFI system partition, read-only.

Reads the FAT32 EFI partition straight from the disk (no mounting, no root
beyond a read ACL) and writes EFI/Microsoft/Boot plus EFI/BOOT/BOOTX64.EFI
into --dest, for start-windows-vm.sh to boot from.

  copy-windows-boot.py --disk /dev/nvme0n1 --dest ~/vm/windows-scanner/esp-copy
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

ESP_TYPE = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"


def esp_offset(disk):
    table = json.loads(subprocess.run(["sfdisk", "-J", disk], capture_output=True, text=True,
                                      check=True).stdout)["partitiontable"]
    sector = table.get("sectorsize", 512)
    for part in table["partitions"]:
        if part["type"].upper() == ESP_TYPE:
            return part["start"] * sector
    sys.exit("No EFI system partition found.")


class Fat32:
    def __init__(self, path, base):
        self.fd, self.base = os.open(path, os.O_RDONLY), base
        bs = self.read(base, 512)
        bps, spc, reserved, fats = struct.unpack_from("<HBHB", bs, 11)
        fat_size, self.root = struct.unpack_from("<I", bs, 36)[0], struct.unpack_from("<I", bs, 44)[0]
        self.fat = base + reserved * bps
        self.data = self.fat + fats * fat_size * bps
        self.cluster = bps * spc

    def read(self, offset, n):
        return os.pread(self.fd, n, offset)

    def chain(self, c):
        while 2 <= c < 0x0FFFFFF8:
            yield c
            c = struct.unpack("<I", self.read(self.fat + c * 4, 4))[0] & 0x0FFFFFFF

    def contents(self, c):
        return b"".join(self.read(self.data + (x - 2) * self.cluster, self.cluster) for x in self.chain(c))

    def entries(self, c):
        raw, lfn = self.contents(c), {}
        for i in range(0, len(raw), 32):
            e = raw[i:i + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn = {}
                continue
            if e[11] == 0x0F:
                lfn[e[0] & 0x1F] = (e[1:11] + e[14:26] + e[28:32]).decode("utf-16-le", "ignore").split("\x00")[0]
                continue
            if e[11] & 0x08:
                lfn = {}
                continue
            short = e[0:8].decode(errors="replace").strip()
            ext = e[8:11].decode(errors="replace").strip()
            name = "".join(lfn[k] for k in sorted(lfn)) if lfn else short + ("." + ext if ext else "")
            lfn = {}
            if name in (".", ".."):
                continue
            cluster = (struct.unpack_from("<H", e, 20)[0] << 16) | struct.unpack_from("<H", e, 26)[0]
            yield name, bool(e[11] & 0x10), cluster, struct.unpack_from("<I", e, 28)[0]

    def find(self, c, name):
        for entry in self.entries(c):
            if entry[0].lower() == name.lower():
                return entry
        sys.exit(f"{name} not found on the EFI partition.")

    def copy(self, c, dest):
        os.makedirs(dest, exist_ok=True)
        for name, is_dir, cluster, size in self.entries(c):
            path = os.path.join(dest, name)
            if is_dir:
                self.copy(cluster, path)
            else:
                with open(path, "wb") as f:
                    f.write(self.contents(cluster)[:size])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disk", default="/dev/nvme0n1")
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    fs = Fat32(args.disk, esp_offset(args.disk))
    efi = fs.find(fs.root, "EFI")
    boot = fs.find(fs.find(efi[2], "Microsoft")[2], "Boot")
    if os.path.exists(args.dest):
        shutil.rmtree(args.dest)
    target = os.path.join(args.dest, "EFI", "Microsoft", "Boot")
    fs.copy(boot[2], target)
    manager = next(n for n in os.listdir(target) if n.lower() == "bootmgfw.efi")
    os.makedirs(os.path.join(args.dest, "EFI", "BOOT"))
    shutil.copy(os.path.join(target, manager), os.path.join(args.dest, "EFI", "BOOT", "BOOTX64.EFI"))
    print(f"Copied the Windows boot manager to {args.dest}")


if __name__ == "__main__":
    main()
