# -*- mode: python ; coding: utf-8 -*-
# macOS build. Produces dist/KitsDirectPrintAgent.app
# Build with: pyinstaller --clean --noconfirm KitsDirectPrintAgent_mac.spec
# Run ON a Mac (PyInstaller does not cross-compile).

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KitsDirectPrintAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # Set to 'universal2' only if building with a universal2 Python
    # interpreter (e.g. python.org installer or `brew install python` on
    # Apple Silicon with universal2 support). Plain venv Python is usually
    # single-arch (arm64 or x86_64) - leave as None in that case.
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KitsDirectPrintAgent',
)

app = BUNDLE(
    coll,
    name='KitsDirectPrintAgent.app',
    icon='icon.icns',
    bundle_identifier='com.keypressit.kitsdirectprintagent',
    version='1.0.0',
    info_plist={
        'CFBundleName': 'Kits Direct Print Agent',
        'CFBundleDisplayName': 'Kits Direct Print Agent',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13',
        'NSHumanReadableCopyright': 'Copyright (c) Keypress IT Services',
        # This is a background print agent, not a document editor - no
        # Finder file-association / dock-bounce behavior needed beyond
        # standard windowed app defaults.
        'LSApplicationCategoryType': 'public.app-category.utilities',
    },
)
