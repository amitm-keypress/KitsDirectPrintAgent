; Kits Direct Print Agent - Windows Installer Script
; Build with Inno Setup (free): https://jrsoftware.org/isdl.php
;
; HOW TO BUILD THE INSTALLER (one-time, on any Windows PC):
;   1. Run build_windows.bat first (produces dist\KitsDirectPrintAgent.exe)
;   2. Install Inno Setup from the link above
;   3. Right-click this file (installer.iss) -> "Compile"
;      (or open it in the Inno Setup Compiler and press Compile / F9,
;      or run:  iscc installer.iss   from a command line)
;   4. Output: Output\KitsDirectPrintAgentSetup.exe
;
; Give THAT single file to any client. They double-click it, click
; Install, done. No command line needed for the client.
;
; SILENT INSTALL (for scripted/mass deployment):
;   KitsDirectPrintAgentSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
; Fully unattended, no UI shown, no reboot prompts.

#define MyAppName "Kits Direct Print Agent"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Keypress IT Services"
#define MyAppExeName "KitsDirectPrintAgent.exe"

[Setup]
AppId={{B7E2B7B1-2E0A-4C6D-9B1E-9E7C7A7B1A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://keypressit.com
AppSupportURL=https://keypressit.com
AppUpdatesURL=https://keypressit.com
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=KitsDirectPrintAgentSetup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start automatically when Windows starts"; GroupDescription: "Startup:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
