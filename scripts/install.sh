#!/usr/bin/env bash
# Install the helper scripts to ~/.local/bin and two menu entries:
# "Document Scanner (LiDE 100)" (simple-scan on the patched backend) and
# "Colour Scan (LiDE 100)". LIDE100_LANG=fa gives Persian names and messages.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
bin="$HOME/.local/bin"
apps="$HOME/.local/share/applications"
lang=${LIDE100_LANG:-${LANG%%_*}}

mkdir -p "$bin" "$apps"
for f in lide100-env scan-color lide100-strip-profile.py; do
    install -m 755 "$repo/scripts/$f" "$bin/$f"
done

if [[ $lang == fa ]]; then
    scanner_name="اسکنر اسناد (کانن LiDE 100)"
    colour_name="اسکن رنگی"
    colour_exec="env LIDE100_LANG=fa $bin/scan-color"
else
    scanner_name="Document Scanner (LiDE 100)"
    colour_name="Colour Scan (LiDE 100)"
    colour_exec="$bin/scan-color"
fi

cat > "$apps/simple-scan-lide100.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$scanner_name
Name[fa]=اسکنر اسناد (کانن LiDE 100)
Comment=Document Scanner with the patched Canon LiDE 100 backend
Keywords=scan;scanner;document;canon;lide;
Exec=$bin/lide100-env simple-scan
Icon=org.gnome.SimpleScan
Terminal=false
Categories=Graphics;Scanning;
EOF

cat > "$apps/scan-color.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$colour_name
Name[fa]=اسکن رنگی
Comment=Colour scan with the Canon LiDE 100
Keywords=scan;scanner;color;colour;canon;
Exec=$colour_exec
Icon=scanner
Terminal=false
Categories=Graphics;Scanning;
EOF

update-desktop-database "$apps" 2>/dev/null || true
echo "Installed lide100-env, scan-color and lide100-strip-profile.py to $bin"
echo "and two menu entries to $apps."
