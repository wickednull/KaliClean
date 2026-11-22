#!/usr/bin/env bash
# Remove a system install made with install.sh (or a manually installed .deb).
# Usage: sudo ./uninstall.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "This uninstaller needs root privileges: sudo ./uninstall.sh" >&2
    exit 1
fi

# If installed via apt/dpkg, let the package manager handle removal instead.
if command -v dpkg-query >/dev/null 2>&1 && dpkg-query -W -f='${Status}' kaliclean 2>/dev/null | grep -q 'install ok installed'; then
    echo "KaliClean is installed as a package; use: sudo apt remove kaliclean" >&2
    exit 1
fi

rm -rf /usr/share/kaliclean
rm -f /usr/bin/kaliclean
rm -f /usr/share/applications/com.github.wickednull.KaliClean.desktop
rm -f /usr/share/metainfo/com.github.wickednull.KaliClean.metainfo.xml
rm -f /usr/share/icons/hicolor/scalable/apps/kaliclean.svg
for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 256x256 512x512; do
    rm -f "/usr/share/icons/hicolor/$size/apps/kaliclean.png"
done
rm -rf /usr/share/doc/kaliclean
rm -f /usr/share/man/man1/kaliclean.1 /usr/share/man/man1/kaliclean.1.gz

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi

echo "KaliClean removed."
