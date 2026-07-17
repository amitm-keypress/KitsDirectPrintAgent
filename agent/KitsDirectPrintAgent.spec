# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller KitsDirectPrintAgent.spec  (run on Windows, see build_windows.bat)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pywin32 modules used by printer.py / win32 backend, not always
        # auto-detected by PyInstaller's static analysis.
        'win32print',
        'win32api',
        'win32con',
        'win32timezone',
        'win32ctypes.pywin32',
        'win32ctypes.pywin32.pywintypes',
        'win32ctypes.pywin32.win32api',
        'pywintypes',
        'pythoncom',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='KitsDirectPrintAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version='version_info.txt',
)
