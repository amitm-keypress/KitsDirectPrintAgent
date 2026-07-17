# Build & Packaging Guide

No application code changed for this. Only packaging files added/updated:
`KitsDirectPrintAgent.spec`, `KitsDirectPrintAgent_mac.spec`, `version_info.txt`,
`icon.ico` / `icon.icns` / `icon.png`, `build_windows.bat`, `build_linux.sh`,
`build_deb.sh`, `build_macos.sh`, `installer.iss`, `.github/workflows/*.yml`.

Each platform must be built ON that platform (PyInstaller does not
cross-compile). Use the GitHub Actions workflows if you don't have all
three machines — they build all 3 automatically.

## Windows

```cmd
build_windows.bat
iscc installer.iss
```
Outputs: `dist\KitsDirectPrintAgent.exe`, `Output\KitsDirectPrintAgentSetup.exe`

Silent install: `KitsDirectPrintAgentSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`

Requires: Python 3.12+, Inno Setup 6 (https://jrsoftware.org/isdl.php).

## Linux

```bash
./build_linux.sh
./build_deb.sh
```
Outputs: `dist/KitsDirectPrintAgent` (standalone binary), `dist/kits-direct-print-agent_1.0.0_amd64.deb`

Install: `sudo dpkg -i dist/kits-direct-print-agent_1.0.0_amd64.deb`
Uninstall: `sudo dpkg -r kits-direct-print-agent`

Installs to `/opt/kits-direct-print-agent/`, adds an app-menu launcher and icon.
Built/tested against Debian/Ubuntu; the `.deb` won't install directly on
Fedora/Arch, but the raw `dist/KitsDirectPrintAgent` binary runs on any
x86_64 Linux distro with CUPS installed (`install.sh` handles that setup).

## macOS

```bash
./build_macos.sh
```
Outputs: `dist/KitsDirectPrintAgent.app`, `dist/KitsDirectPrintAgent-1.0.0.dmg`, `dist/KitsDirectPrintAgent-1.0.0.pkg`

App is unsigned/unnotarized (no Apple Developer cert supplied). First launch
on a client Mac: right-click the app → Open → Open (one-time Gatekeeper
prompt). Signing/notarizing later needs an Apple Developer ID cert — not a
packaging-only change, ask if you want that added.

Builds native to whatever Mac/runner architecture you build on (arm64 on
Apple Silicon, x86_64 on Intel). A single `universal2` binary needs a
universal2 Python interpreter, not the default venv Python.

Silent install via .pkg: `installer -pkg KitsDirectPrintAgent-1.0.0.pkg -target /`

## CI/CD (GitHub Actions)

Three workflows in `.github/workflows/`: `build-windows.yml`,
`build-linux.yml`, `build-macos.yml`. Each runs on push to `main`, on PRs,
and manually (workflow_dispatch). Pushing a tag like `v1.0.0` also attaches
the built artifacts to a GitHub Release automatically (all three OSes).
