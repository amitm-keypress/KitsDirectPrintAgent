#!/usr/bin/env bash
# Build KitsDirectPrintAgent.app + .dmg on macOS.
# Run this ON a Mac with Python 3.12+ installed (brew install python@3.12).
# PyInstaller does NOT cross-compile - this must run on real macOS hardware
# (or a macOS CI runner, see .github/workflows/build-macos.yml).
set -euo pipefail

APP_NAME="KitsDirectPrintAgent"
VERSION="1.0.0"

if ! command -v python3 &> /dev/null; then
    echo "python3 not found. Install it (brew install python@3.12) and retry."
    exit 1
fi

# pycups needs CUPS dev headers - usually preinstalled on macOS, but ensure Xcode CLT is present
if ! xcode-select -p &> /dev/null; then
    echo "Xcode Command Line Tools not found, installing..."
    xcode-select --install
fi

python3 -m venv build_venv
source build_venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

rm -rf build dist

pyinstaller --clean --noconfirm KitsDirectPrintAgent_mac.spec

if [ ! -d "dist/${APP_NAME}.app" ]; then
    echo "Build FAILED - dist/${APP_NAME}.app was not produced."
    deactivate
    exit 1
fi

echo
echo "Build complete: dist/${APP_NAME}.app"
echo "Note: this app is unsigned/unnotarized. First launch on a client Mac"
echo "needs: right-click the app -> Open -> Open (Gatekeeper warning, one-time)."

# ---------------------------------------------------------------------------
# Package into a .dmg (drag-to-Applications installer)
# ---------------------------------------------------------------------------
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
rm -f "dist/${DMG_NAME}"

STAGING_DIR="dist/dmg_staging"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "dist/${APP_NAME}.app" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create -volname "${APP_NAME}" \
    -srcfolder "$STAGING_DIR" \
    -ov -format UDZO \
    "dist/${DMG_NAME}"

rm -rf "$STAGING_DIR"

echo "Built: dist/${DMG_NAME}"

# ---------------------------------------------------------------------------
# Optional: also build a .pkg installer (silent-install friendly:
#   installer -pkg KitsDirectPrintAgent.pkg -target /
# ---------------------------------------------------------------------------
PKG_NAME="${APP_NAME}-${VERSION}.pkg"
rm -f "dist/${PKG_NAME}"

pkgbuild --install-location /Applications \
    --component "dist/${APP_NAME}.app" \
    --identifier com.keypressit.kitsdirectprintagent \
    --version "${VERSION}" \
    "dist/${PKG_NAME}"

echo "Built: dist/${PKG_NAME}"
echo
echo "Give clients EITHER the .dmg (drag to Applications) OR the .pkg"
echo "(double-click installer, or silent: installer -pkg ${PKG_NAME} -target /)."

deactivate
