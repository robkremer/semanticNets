#!/usr/bin/env bash
# Make the Linux AppImage, dist/SemanticNets-VERSION-ARCH.AppImage, from the
# PyInstaller build ("dist/Semantic Nets/", made by packaging/semanticNets.spec):
# one file that runs on most Linuxes with a glibc at least as new as the one it
# was built on (build on the oldest Linux to be supported: eg, Ubuntu 22.04).
#
#   packaging/appimage.sh VERSION [APPIMAGETOOL]
#
# APPIMAGETOOL is appimagetool's AppImage (default: appimagetool, on the PATH):
# https://github.com/AppImage/appimagetool/releases. Where there's no FUSE (eg,
# in a container), set APPIMAGE_EXTRACT_AND_RUN=1.
#
# The AppImage has a .desktop file (the Semantic Nets entry in the menus), the
# icon, and the MIME types of .snm and .snv files, for tools that install
# AppImages (eg, Gear Lever, AppImageLauncher) to register.
set -euo pipefail

version="${1:?usage: appimage.sh VERSION [APPIMAGETOOL]}"
tool="${2:-appimagetool}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
built="$root/dist/Semantic Nets"
arch="$(uname -m)"
appdir="$root/build/SemanticNets.AppDir"
out="$root/dist/SemanticNets-$version-$arch.AppImage"

[ -x "$built/semantic-nets" ] || { echo "No PyInstaller build in \"$built\": run PyInstaller on packaging/semanticNets.spec first." >&2; exit 1; }

rm -rf "$appdir"
mkdir -p "$appdir/usr/lib" "$appdir/usr/share/mime/packages" "$appdir/usr/share/applications" \
         "$appdir/usr/share/icons/hicolor/256x256/apps"
cp -a "$built" "$appdir/usr/lib/semantic-nets"

cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
here="$(dirname "$(readlink -f "$0")")"
exec "$here/usr/lib/semantic-nets/semantic-nets" "$@"
EOF
chmod +x "$appdir/AppRun"

cat > "$appdir/semantic-nets.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Semantic Nets
Comment=Editor for typed semantic networks, with a reasoner
Exec=semantic-nets %F
Icon=semantic-nets
Categories=Education;Science;
MimeType=application/x-semantic-nets-model;application/x-semantic-nets-view;
Terminal=false
X-AppImage-Version=$version
EOF
cp "$appdir/semantic-nets.desktop" "$appdir/usr/share/applications/"

cp "$here/sn-icon.png" "$appdir/semantic-nets.png"
cp "$here/sn-icon.png" "$appdir/usr/share/icons/hicolor/256x256/apps/semantic-nets.png"
ln -sf semantic-nets.png "$appdir/.DirIcon"

cat > "$appdir/usr/share/mime/packages/semantic-nets.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-semantic-nets-model">
    <comment>Semantic Nets model</comment>
    <glob pattern="*.snm"/>
  </mime-type>
  <mime-type type="application/x-semantic-nets-view">
    <comment>Semantic Nets view</comment>
    <glob pattern="*.snv"/>
  </mime-type>
</mime-info>
EOF

rm -f "$out"
ARCH="$arch" "$tool" --no-appstream "$appdir" "$out"
echo "Made $out"
