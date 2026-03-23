; Bundle 1.0.0 — exe, assets și acest script sunt în același folder.
; Build installer: compile_installers.bat (din acest folder).
#define MyAppName "Naturen Admin"
#define MyAppVersion "1.0.0"
#define MyAppExe "Naturen Admin 1.0.0.exe"
#define MyAppPublisher "Naturen"

[Setup]
AppId={{A1C3E5F7-9B2D-4E6F-8A0C-1D3F5B7E9A2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NaturenFlow
DefaultGroupName={#MyAppName}
OutputDir=installer
OutputBaseFilename=Naturen_Admin_{#MyAppVersion}_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
