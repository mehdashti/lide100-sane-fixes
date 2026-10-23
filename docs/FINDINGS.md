# What was wrong, and how it was found

Scanner: Canon CanoScan LiDE 100 (USB `04a9:1904`, Genesys GL847 ASIC, CIS sensor).
Software: SANE 1.4.0 genesys backend on Debian.

## Symptoms

- Colour scans at any resolution had three soft-edged **yellow vertical stripes**
  (around 20–80, 920–1270 and 2330–2470 px at 300 dpi, the same physical places at
  every resolution). Grey scans were clean; 16-bit colour scans had faint blue bands
  instead.
- Bright edges, such as the rim of a plastic ID card, got a row of **red, yellow and
  magenta speckles**.
- Even with those fixed, colours looked **dull** next to the Canon Windows driver.

## Method

The Windows 11 install on the same machine was booted inside QEMU straight from the
physical disk (read-only backing image plus a qcow2 overlay, so nothing was written
to the disk), with the scanner passed through by `usb-host` and QEMU's `pcap=` option
recording every USB transfer. `tools/usbcap.py` decodes such a capture into register
writes, buffer uploads and scan starts. The same scans were then made with SANE at
`SANE_DEBUG_GENESYS=255`, and the backend's calibration data saved with
`SANE_DEBUG_GENESYS_IMAGE=1`, to compare the two drivers.

Only register traffic and the scanner's own data were observed; no Canon code was
decompiled, and nothing from the Canon driver is included here.

## Findings

### 1. The last gamma table entry is 0 (the stripes and the speckles)

`sanei_genesys_send_gamma_table()` sets the last word of each gamma table to 0, with
a FIXME saying the right value is probably full scale. That word is the output for
the top of the input range, so a channel that reaches full scale comes out **black**:

- where blue is over-corrected (finding 2), blue hits full scale, becomes 0, and white
  paper turns yellow;
- at a glossy edge one channel hits full scale and the pixel turns red, yellow or
  magenta.

Proof: with a flat shading table uploaded, raw blue in the stripe columns was normal
(about 230/255); with the normal table it was 0. After the fix it is 255, and with the
strip profile it is back to about 235. A card edge that gave 2062 speckle pixels in a
strip gave 0 afterwards. 16-bit scans were never affected because they bypass the
gamma table.

Fix: `patches/0001`. This one probably affects every scanner that uses this function
(GL847 and GL124 based Canon LiDE models).

### 2. The internal white strip has yellowed

Before each scan the scanner reads a white strip inside the housing to compute
per-column gain. Read in the backend's planar layout, the strip's blue/green ratio is
0.99 in normal columns but **0.76–0.86 in the three stripe regions**, along its whole
length (0–5 mm). The same columns on white paper have a normal ratio of 0.98–0.99. So
the strip has yellowed there, and the backend boosts blue by 20–30% in those columns.

The Windows driver uploads the same kind of boosted coefficients (its first captured
entries show blue/green gain ratios of about 1.3 in the left band), so it relies on its
own later processing to hide it.

Fix: `patches/0003` plus `scripts/lide100-strip-profile.py`. The script calibrates once
on the strip and once on white paper (moving the shading scan there with
`LIDE100_CALIB_Y`/`LIDE100_CALIB_MM`) and stores the per-column paper/strip ratio. The
backend applies it to the strip reading before computing coefficients. The profile is
specific to each scanner.

### 3. The Windows driver's settings

From the capture, compared with SANE for the same 300 dpi colour scan:

| | Canon Windows driver | SANE 1.4.0 |
|---|---|---|
| LED exposure R/G/B | 449 / 397 / 345 (same for every scan) | 347 / 224 / 207 (LED calibration to ~30k) |
| AFE gain/offset | identical | identical |
| Pixel averaging (`REG_0x03_AVEENB`) | on | off |
| Gamma | 2.2, input levels 400..58000 (57500 blue) | 2.2, input levels 0..65535 |

The exposure difference was not the cause of the stripes (matching it alone changed
nothing), but it gives a better signal. The gamma input levels are what made SANE's
output look dull: white paper came out at about 233/255 instead of about 241.

Fix: `patches/0002`.

## Limits

- Tested on one LiDE 100, at 150 and 300 dpi, on SANE 1.4.0.
- The exposure targets and gamma levels come from that unit's Windows driver.
- Canon ScanGear also processes images on the PC (unsharp mask, automatic tone); that
  is not visible over USB and is not reproduced.
