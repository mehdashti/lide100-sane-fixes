#!/usr/bin/env python3
"""Create the white strip correction profile for a Canon LiDE 100.

The scanner calibrates on a white strip inside its housing. On older units the
strip can yellow in places, which makes blue too strong in those columns. The
patched genesys backend reads a per-column correction from
~/.sane/canon-lide-100-strip-profile.txt. This script makes it: it calibrates
once on the strip and once on clean white paper lying on the glass, and stores
the per-column ratio between the two.

Put a clean, plain white A4 sheet on the glass, close the lid, then run:
    lide100-strip-profile.py [--output PATH]
"""
import argparse
import os
import statistics
import subprocess
import sys
import tempfile

PREFIX = os.environ.get("LIDE100_SANE_PREFIX", os.path.expanduser("~/.local/lib/sane-lide100"))
# Where on the paper to calibrate, in mm from the scanner's home position (the
# page starts at 8.3 mm), and how much of the page to take the median over.
PAPER_Y_MM, PAPER_MM = 100, 20


def read_planar_pnm(path):
    """Return (width, height, sample(c, x, y)) for the backend's 16-bit debug
    images, which store each row as a red block, a green block and a blue block."""
    data = open(path, "rb").read()
    fields, i = [], 0
    while len(fields) < 4:
        while data[i:i + 1].isspace():
            i += 1
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        fields.append(data[i:j])
        i = j
    width, height = int(fields[1]), int(fields[2])
    pixels = data[i + 1:]

    def sample(c, x, y=0):
        o = (y * width * 3 + c * width + x) * 2
        return int.from_bytes(pixels[o:o + 2], "big")

    return width, height, sample


def calibrate(workdir, extra_env):
    env = dict(os.environ, LD_LIBRARY_PATH=f"{PREFIX}/lib", SANE_CONFIG_DIR=f"{PREFIX}/etc/sane.d",
               SANE_DEBUG_GENESYS_IMAGE="1", LIDE100_STRIP_PROFILE="/nonexistent", **extra_env)
    scanimage = f"{PREFIX}/bin/scanimage"
    if not os.path.exists(scanimage):
        sys.exit(f"{scanimage} not found. Run scripts/build.sh first.")
    devices = subprocess.run([scanimage, "-f", "%d%n"], env=env, capture_output=True, text=True).stdout
    device = next((d for d in devices.split() if d.startswith("genesys:")), None)
    if not device:
        sys.exit("Scanner not found. Check the USB cable.")
    # A small scan is enough: what we need is the calibration the backend runs first.
    subprocess.run([scanimage, "-d", device, "--force-calibration", "--resolution", "300",
                    "--mode", "Color", "-t", "120", "-y", "5", "--format=pnm", "-o", "scan.pnm"],
                   env=env, cwd=workdir, check=True, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=os.path.expanduser("~/.sane/canon-lide-100-strip-profile.txt"))
    parser.add_argument("--force", action="store_true", help="save even if the paper looks uneven")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as strip_dir, tempfile.TemporaryDirectory() as paper_dir:
        print("Calibrating on the internal white strip...")
        calibrate(strip_dir, {})
        print("Calibrating on the white paper...")
        calibrate(paper_dir, {"LIDE100_CALIB_Y": str(PAPER_Y_MM), "LIDE100_CALIB_MM": str(PAPER_MM)})

        width, _, strip_white = read_planar_pnm(f"{strip_dir}/gl_white_average.tiff.pnm")
        _, _, strip_dark = read_planar_pnm(f"{strip_dir}/gl_black_average.tiff.pnm")
        pw, lines, paper_white = read_planar_pnm(f"{paper_dir}/gl_white_shading.tiff.pnm")
        _, _, paper_dark = read_planar_pnm(f"{paper_dir}/gl_black_average.tiff.pnm")
        if pw != width:
            sys.exit(f"Calibration widths differ ({width} vs {pw}); nothing written.")

        ratio = [[0.0] * width for _ in range(3)]
        uneven, green = set(), [0.0] * width
        for c in range(3):
            for x in range(width):
                # median over the paper lines, so dust specks don't count
                values = [paper_white(c, x, y) for y in range(lines)]
                paper = statistics.median(values)
                lit_paper = paper - paper_dark(c, x)
                lit_strip = strip_white(c, x) - strip_dark(c, x)
                ratio[c][x] = lit_paper / lit_strip if lit_strip > 1000 and lit_paper > 1000 else 1.0
                if c == 1:
                    green[x] = lit_paper
                    # print or an object on the paper darkens many lines, a speck only a few
                    if sum(v < 0.8 * paper for v in values) > lines // 10:
                        uneven.add(x)

        # ...and something covering most of the lines pulls the whole column down
        inner = range(width // 20, width * 19 // 20)
        typical = statistics.median(green[x] for x in inner)
        uneven = sorted(x for x in inner if x in uneven or green[x] < 0.85 * typical)
        if len(uneven) > width // 100 and not args.force:
            mm = [round(x * 25.4 / 600) for x in (uneven[0], uneven[-1])]
            sys.exit(f"The paper is not evenly white about {mm[0]}-{mm[1]} mm from the left edge, "
                     f"{PAPER_Y_MM - 8}-{PAPER_Y_MM + PAPER_MM - 8} mm from the top of the glass. "
                     "Use a clean, plain white sheet with nothing else on the glass and run again "
                     "(--force saves anyway). Nothing written.")

        profile = [[1.0] * width for _ in range(3)]
        for c in range(3):
            centre = statistics.median(ratio[c][width // 10: width * 9 // 10])
            for x in range(width):
                window = ratio[c][max(0, x - 3): x + 4]
                profile[c][x] = min(1.6, max(0.6, statistics.median(window) / centre))

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        f.write(f"{width}\n")
        for x in range(width):
            f.write(f"{profile[0][x]:.4f} {profile[1][x]:.4f} {profile[2][x]:.4f}\n")

    worst = max(range(width), key=lambda x: abs(profile[2][x] - 1))
    print(f"Saved {args.output}")
    print(f"Strongest blue correction: x{profile[2][worst]:.2f} at column {worst} of {width}.")


if __name__ == "__main__":
    main()
