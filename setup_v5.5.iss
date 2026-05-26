; ============================================================
;  TSS PC Controller - Inno Setup Script
;  Version: 5.5 - FINAL STABLE
; ============================================================

#define MyAppName      "TSS PC Controller"
#define MyAppVersion   "5.5"
#define MyAppPublisher "Tahsin Ahmed Zim"
#define MyAppExeName   "TSS_PC_Controller.exe"

[Setup]
AppId={{D1A3B4C5-E6F7-4890-A1B2-C3D4E5F6A8B9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=TSS_PC_Controller_Setup_v{#MyAppVersion}
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "TSS_PC_Controller_v5.5.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifsilent
Filename: "schtasks"; Parameters: "/create /tn ""TSS_PC_Controller"" /tr ""'{app}\{#MyAppExeName}'"" /sc onlogon /rl highest /f"; Flags: runhidden

[UninstallRun]
Filename: "schtasks"; Parameters: "/delete /tn ""TSS_PC_Controller"" /f"; Flags: runhidden
