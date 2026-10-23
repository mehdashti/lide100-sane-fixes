# lide100-sane-fixes

Unofficial fixes for the **Canon CanoScan LiDE 100** on Linux, as patches to SANE's
genesys backend. Not affiliated with or endorsed by Canon.

[فارسی](README.fa.md)

## What it fixes

- **Yellow vertical stripes** in colour scans.
- **Red, yellow and magenta speckles** along bright edges (card rims, glossy paper).
- **Dull colours** compared with the Canon Windows driver.

The causes, found by recording the Canon Windows driver's USB traffic, are explained in
[docs/FINDINGS.md](docs/FINDINGS.md). In short: SANE sets the last gamma table entry to
0, the scanner's internal white calibration strip yellows with age, and SANE uses
different light and gamma settings than Canon's driver.

| Patch | What it does | Who it is for |
|---|---|---|
| `0001-gamma-full-scale-last-entry` | Full scale instead of 0 as the last gamma entry | Probably all GL847/GL124 Canon LiDE models |
| `0002-lide100-windows-driver-settings` | LED targets, pixel averaging and gamma levels from the Windows driver | LiDE 100 |
| `0003-lide100-white-strip-profile` | Per-column correction for a yellowed calibration strip | LiDE 100 |
| `0004-debug-images-without-libtiff` | Debug images as PNM when built without libtiff (needed by the profile tool) | Everyone building without libtiff |

## Install

Tested on Debian (sid) with sane-backends 1.4.0. The patched backend goes into
`~/.local/lib/sane-lide100`; the system's SANE is not changed.

1. Build tools and headers:

   ```bash
   sudo apt install build-essential autoconf automake autoconf-archive libtool autopoint gettext pkg-config libusb-1.0-0-dev dpkg-dev zenity imagemagick
   ```

2. Build. Without an argument this fetches the source with `apt-get source sane-backends`
   (needs `deb-src` lines in your APT sources); or pass a sane-backends 1.4.0 source directory:

   ```bash
   scripts/build.sh
   ```

3. Install the helpers and menu entries (`LIDE100_LANG=fa` for Persian):

   ```bash
   scripts/install.sh
   ```

4. Put a **clean, plain white A4 sheet** flat on the glass with nothing else under or
   beside it, close the lid, and make the white strip profile for your scanner (takes
   about 1.5 minutes). The tool refuses to save if the paper looks uneven:

   ```bash
   lide100-strip-profile.py
   ```

## Use

- **Document Scanner (LiDE 100)** in the applications menu: GNOME's Document Scanner
  running on the patched backend. The normal Document Scanner keeps using the system
  backend.
- **Colour Scan (LiDE 100)**: asks for the resolution, saves a JPEG to `~/Pictures/Scans`
  and opens it. From a terminal: `SCAN_RESOLUTION=600 scan-color`.
- Any other SANE program: `lide100-env PROGRAM`, for example `lide100-env scanimage -L`.

If the stripes ever come back (for example after cleaning the scanner), make the
profile again.

## Limits

Tested on one scanner, at 150 and 300 dpi. The exposure and gamma values come from
that unit's Windows driver. Reports from other LiDE 100 owners, and from owners of
other LiDE models for patch 0001, are welcome.

## Tools

`tools/` has what was used to find all this: booting the Windows install on the same
machine in QEMU from its own disk (read-only) with the scanner passed through and its
USB traffic recorded (`start-windows-vm.sh`, `copy-windows-boot.py`), and a decoder for
those captures (`usbcap.py`). Never publish such captures: they contain fragments of
whatever was scanned.

## License

GPL-2.0-or-later, like SANE. See [LICENSE](LICENSE).
