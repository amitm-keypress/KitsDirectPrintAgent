#!/usr/bin/env bash
# One-shot installer for Kits Direct Print Agent on a client Linux machine.
# Installs ALL required system libraries, then installs the app itself.
#
# Usage:
#   ./install.sh                 -> installs binary from ./dist/KitsDirectPrintAgent
#   ./install.sh --from-source   -> installs Python + deps and runs from source instead

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/kits-direct-print-agent"
BIN_NAME="KitsDirectPrintAgent"

echo "== Kits Direct Print Agent installer =="

if [ "$EUID" -ne 0 ]; then
    echo "Re-run with sudo (needed to install system packages and copy to /opt)."
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. System libraries required at runtime (and build, if --from-source)
#    - libcups2 / cups        : printer discovery (pycups)
#    - python3-tk             : GUI (tkinter) - only needed for --from-source
#    - ca-certificates        : HTTPS calls to Odoo over TLS
# ---------------------------------------------------------------------------
echo "Installing system libraries..."
apt update
apt install -y libcups2 cups ca-certificates

if ! systemctl is-active --quiet cups 2>/dev/null; then
    echo "Starting CUPS service..."
    systemctl enable --now cups || echo "Could not start cups automatically, start it manually."
fi

# ---------------------------------------------------------------------------
# 2. App install
# ---------------------------------------------------------------------------
mkdir -p "$INSTALL_DIR"

if [ "${1:-}" = "--from-source" ]; then
    echo "Installing from source (Python + all pip deps)..."
    apt install -y python3-venv python3-dev python3-tk libcups2-dev

    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR"/
    cd "$INSTALL_DIR"

    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt

    cat > "$INSTALL_DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
./venv/bin/python3 main.py
EOF
    chmod +x "$INSTALL_DIR/run.sh"
    EXEC_PATH="$INSTALL_DIR/run.sh"
else
    if [ ! -f "$SCRIPT_DIR/dist/$BIN_NAME" ]; then
        echo "dist/$BIN_NAME not found. Build it first with build_linux.sh,"
        echo "or run this installer with --from-source."
        exit 1
    fi
    cp "$SCRIPT_DIR/dist/$BIN_NAME" "$INSTALL_DIR/$BIN_NAME"
    chmod +x "$INSTALL_DIR/$BIN_NAME"
    EXEC_PATH="$INSTALL_DIR/$BIN_NAME"
fi

# ---------------------------------------------------------------------------
# 3. Desktop entry + autostart
# ---------------------------------------------------------------------------
mkdir -p /usr/share/icons/hicolor/256x256/apps
if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" /usr/share/icons/hicolor/256x256/apps/kits-direct-print-agent.png
fi

cat > /usr/share/applications/kits-direct-print-agent.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Kits Direct Print Agent
Comment=Odoo Direct Print desktop agent
Exec=$EXEC_PATH
Icon=kits-direct-print-agent
Terminal=false
Categories=Utility;
EOF

REAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
mkdir -p "$USER_HOME/.config/autostart"
cp /usr/share/applications/kits-direct-print-agent.desktop "$USER_HOME/.config/autostart/"
chown "$REAL_USER:$REAL_USER" "$USER_HOME/.config/autostart/kits-direct-print-agent.desktop"

echo
echo "Done. Installed to: $INSTALL_DIR"
echo "Launch from app menu, or run: $EXEC_PATH"
echo "Will also auto-start on next login for user: $REAL_USER"
