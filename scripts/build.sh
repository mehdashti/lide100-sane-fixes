#!/usr/bin/env bash
# Build SANE's genesys backend with the LiDE 100 patches into a private prefix.
#
#   scripts/build.sh                 fetch Debian/Ubuntu's source with `apt-get source`
#   scripts/build.sh SOURCE_DIR      use an existing sane-backends 1.4.0 source tree
#
# PREFIX (default ~/.local/lib/sane-lide100) receives the result; the system
# SANE is not touched. WORKDIR (default ~/.cache/lide100-sane-build) holds the
# fetched source.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
prefix=${PREFIX:-$HOME/.local/lib/sane-lide100}
work=${WORKDIR:-$HOME/.cache/lide100-sane-build}

if [[ $# -ge 1 ]]; then
    src=$(cd "$1" && pwd)
else
    mkdir -p "$work"
    cd "$work"
    rm -rf sane-backends-*/
    apt-get source sane-backends
    src=$(ls -d "$work"/sane-backends-*/ | head -n 1)
fi
cd "$src"

for p in "$repo"/patches/*.patch; do
    if patch -p1 -R -s -f --dry-run < "$p" >/dev/null 2>&1; then
        echo "already applied: $(basename "$p")"
    else
        patch -p1 -s < "$p"
        echo "applied: $(basename "$p")"
    fi
done

# configure.ac uses two macros from autoconf-archive. Without that package,
# stand in for them: GCC defaults to C++17 and glibc's <stdint.h> is complete.
if [[ ! -e "$(aclocal --print-ac-dir)/ax_create_stdint_h.m4" ]]; then
    cp "$repo/scripts/ax-stubs.m4" m4/local-ax-stubs.m4
fi

./autogen.sh
./configure --prefix="$prefix" BACKENDS=genesys --disable-locking --disable-nls \
    --without-avahi --without-snmp --without-libcurl --without-poppler-glib
make -j"$(nproc)"
make install

echo
echo "Installed to $prefix"
echo "Next: scripts/install.sh, then lide100-strip-profile.py with white paper on the glass."
