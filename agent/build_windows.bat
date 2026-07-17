@echo off
REM Build KitsDirectPrintAgent.exe on Windows.
REM Run this ON a Windows machine with Python 3.12+ installed.
REM Produces: dist\KitsDirectPrintAgent.exe  (standalone, no Python required to run it)

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.12+ and retry.
    exit /b 1
)

python -m venv build_venv
call build_venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pyinstaller-hooks-contrib

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

REM Build from the .spec file so the custom icon, version info, and
REM pywin32 hidden imports below are applied. Do not switch back to a
REM plain "pyinstaller main.py" command line build.
pyinstaller --clean --noconfirm KitsDirectPrintAgent.spec

if not exist dist\KitsDirectPrintAgent.exe (
    echo Build FAILED - dist\KitsDirectPrintAgent.exe was not produced.
    deactivate
    exit /b 1
)

echo.
echo Build complete: dist\KitsDirectPrintAgent.exe
echo Next step: open installer.iss in Inno Setup and press Compile
echo            (or run:  iscc installer.iss   if ISCC.exe is on PATH)
echo to produce Output\KitsDirectPrintAgentSetup.exe

deactivate
endlocal
