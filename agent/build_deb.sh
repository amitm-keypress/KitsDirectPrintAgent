#!/usr/bin/env bash
# Builds kits-direct-print-agent_1.0.0_amd64.deb
# Prereq: run ./build_linux.sh first to produce dist/KitsDirectPrintAgent
#
# Self-contained: builds the whole DEBIAN package tree from scratch each
# run (no pre-existing deb_package/ directory required).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="1.0.0"
PKG_NAME="kits-direct-print-agent"
BIN_SRC="$SCRIPT_DIR/dist/KitsDirectPrintAgent"
BUILD_ROOT="$SCRIPT_DIR/deb_package/${PKG_NAME}_${VERSION}"

if [ ! -f "$BIN_SRC" ]; then
    echo "dist/KitsDirectPrintAgent not found."
    echo "Run ./build_linux.sh first to build the binary, then re-run this script."
    exit 1
fi

if ! command -v dpkg-deb &> /dev/null; then
    echo "dpkg-deb not found. Install with: sudo apt install dpkg-dev"
    exit 1
fi

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT/DEBIAN"
mkdir -p "$BUILD_ROOT/opt/${PKG_NAME}"
mkdir -p "$BUILD_ROOT/usr/share/applications"
mkdir -p "$BUILD_ROOT/usr/share/icons/hicolor/256x256/apps"

# --- binary -----------------------------------------------------------
cp "$BIN_SRC" "$BUILD_ROOT/opt/${PKG_NAME}/KitsDirectPrintAgent"
chmod +x "$BUILD_ROOT/opt/${PKG_NAME}/KitsDirectPrintAgent"

# --- icon ---------------------------------------------------------------
cp "$SCRIPT_DIR/icon.png" "$BUILD_ROOT/usr/share/icons/hicolor/256x256/apps/${PKG_NAME}.png"

# --- desktop launcher -----------------------------------------------------
cat > "$BUILD_ROOT/usr/share/applications/${PKG_NAME}.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Kits Direct Print Agent
Comment=Odoo Direct Print desktop agent
Exec=/opt/${PKG_NAME}/KitsDirectPrintAgent
Icon=${PKG_NAME}
Terminal=false
Categories=Utility;
DESKTOP

# --- control ------------------------------------------------------------
cat > "$BUILD_ROOT/DEBIAN/control" <<CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: libcups2, ca-certificates
Maintainer: Keypress IT Services <support@keypressit.com>
Description: Kits Direct Print Agent
 Desktop agent for the Odoo kits_direct_print module. Discovers local
 and network printers and silently prints jobs pushed from Odoo.
CONTROL

# --- postinst (register icon/desktop db, start service) ------------------
cat > "$BUILD_ROOT/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
POSTINST
chmod +x "$BUILD_ROOT/DEBIAN/postinst"

# --- prerm (clean up on uninstall) ---------------------------------------
cat > "$BUILD_ROOT/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
exit 0
PRERM
chmod +x "$BUILD_ROOT/DEBIAN/prerm"

# --- postrm (final cache refresh after removal) ---------------------------
cat > "$BUILD_ROOT/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
POSTRM
chmod +x "$BUILD_ROOT/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$BUILD_ROOT" \
    "$SCRIPT_DIR/dist/${PKG_NAME}_${VERSION}_amd64.deb"

echo
echo "Built: dist/${PKG_NAME}_${VERSION}_amd64.deb"
echo "Install:   sudo dpkg -i dist/${PKG_NAME}_${VERSION}_amd64.deb"
echo "Uninstall: sudo dpkg -r ${PKG_NAME}"
