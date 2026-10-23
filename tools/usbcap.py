#!/usr/bin/env python3
"""Decode a QEMU usbmon pcap of the Canon LiDE 100 (Genesys GL847) into a
readable log of register writes/reads, buffer transfers and scan starts.

  usbcap.py CAPTURE.pcap            full log
  usbcap.py CAPTURE.pcap --scans    register state at each scan start

Protocol bits, as seen in the capture and in SANE's genesys backend:
  ctrl 0x40/0x04 value 0x83, data [reg, val, reg, val, ...]  -> register writes
  ctrl 0xc0/0x04 value 0x8e, index (reg << 8) | 0x22         -> register read
  ctrl 0x40/0x04 value 0x82, 8-byte header, then bulk OUT    -> buffer write
  bulk IN on ep 0x81                                         -> image/calibration data
"""
import struct
import sys

XFER = {0: "iso", 1: "intr", 2: "ctrl", 3: "bulk"}


def packets(path):
    d = open(path, "rb").read()
    if struct.unpack_from("<I", d, 0)[0] != 0xA1B2C3D4 or struct.unpack_from("<I", d, 20)[0] != 220:
        sys.exit("not a usbmon (linktype 220) pcap")
    off = 24
    while off + 16 <= len(d):
        ts, tus, incl, _ = struct.unpack_from("<IIII", d, off)
        off += 16
        pkt = d[off:off + incl]
        off += incl
        if len(pkt) < 64:
            break
        yield {
            "id": struct.unpack_from("<Q", pkt, 0)[0],
            "t": ts + tus / 1e6,
            "type": chr(pkt[8]),
            "xfer": XFER[pkt[9]],
            "ep": pkt[10],
            "status": struct.unpack_from("<i", pkt, 28)[0],
            "length": struct.unpack_from("<I", pkt, 32)[0],
            "setup": pkt[40:48],
            "data": pkt[64:],
        }


def events(path):
    """Pair each submit with its completion and yield decoded events."""
    pending = {}
    t0 = None
    for p in packets(path):
        if t0 is None:
            t0 = p["t"]
        if p["type"] == "S":
            pending[p["id"]] = p
            continue
        s = pending.pop(p["id"], None)
        if s is None:
            continue
        t = s["t"] - t0
        if s["xfer"] == "ctrl":
            rt, req, val, idx, ln = struct.unpack("<BBHHH", s["setup"])
            if rt == 0x40 and req == 0x04 and val == 0x83:
                body = s["data"]
                for i in range(0, len(body) - 1, 2):
                    yield t, "W", body[i], body[i + 1]
            elif rt == 0xC0 and req == 0x04 and val == 0x8E and idx & 0xFF == 0x22:
                yield t, "R", idx >> 8, p["data"][0] if p["data"] else None
            elif rt == 0x40 and req == 0x04 and val == 0x82:
                yield t, "BUFHDR", s["data"].hex(), None
            elif rt & 0x60 == 0x40:  # other vendor requests
                yield t, "CTRL", f"{rt:#04x} req={req:#04x} val={val:#06x} idx={idx:#06x}", (s["data"] or p["data"]).hex()
        elif s["xfer"] == "bulk":
            if s["ep"] & 0x80:
                yield t, "BULKIN", p["length"], p["data"][:16].hex()
            else:
                yield t, "BULKOUT", s["length"], s["data"][:16].hex()


def main():
    path = sys.argv[1]
    regs = {}
    scans = 0
    show_scans = "--scans" in sys.argv
    bulk_in = 0
    for t, kind, a, b in events(path):
        if kind == "W":
            regs[a] = b
            # GL847: a non-zero write to register 0x0f starts the scan (Windows writes 0xff)
            if a == 0x0F and b != 0x00:
                scans += 1
                if show_scans:
                    print(f"\n=== scan start #{scans} at {t:.3f}s ===")
                    for r in sorted(regs):
                        print(f"  reg 0x{r:02x} = 0x{regs[r]:02x}")
        if show_scans:
            continue
        if kind == "W":
            print(f"{t:10.3f}  W  0x{a:02x} = 0x{b:02x}" + ("   <-- scan start" if a == 0x0F and b else ""))
        elif kind == "R":
            print(f"{t:10.3f}  R  0x{a:02x} -> " + ("--" if b is None else f"0x{b:02x}"))
        elif kind == "BULKIN":
            bulk_in += a
            print(f"{t:10.3f}  bulk in  {a} bytes")
        elif kind == "BULKOUT":
            print(f"{t:10.3f}  bulk out {a} bytes  {b}")
        else:
            print(f"{t:10.3f}  {kind} {a} {b or ''}")
    print(f"\n# scan starts: {scans}, bulk-in total: {bulk_in / 1e6:.1f} MB", file=sys.stderr)


if __name__ == "__main__":
    main()
