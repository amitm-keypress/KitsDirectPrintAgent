#!/usr/bin/env bash
# Build KitsDirectPrintAgent binary on Linux.
# Run this ON a Linux machine with Python 3.12+, CUPS dev headers, and tk installed.
set -euo pipefail

if ! command -v python3 &> /dev/null; then
    echo "python3 not found. Install it and retry."
    exit 1
fi

# system deps needed to build pycups + tkinter
if command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y python3-venv python3-dev libcups2-dev python3-tk
fi

python3 -m venv build_venv
source build_venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

rm -rf build dist

pyinstaller --onefile --windowed --name "KitsDirectPrintAgent" \
    --icon=icon.png \
    main.py

echo
echo "Build complete: dist/KitsDirectPrintAgent"
echo "Copy that single file to the client machine, chmod +x, run it."

deactivate
