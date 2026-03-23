; Bundle 1.0.0 — update Flow (exe + assets în același folder ca setup_flow.iss).
#define MyAppName "Naturen Flow"
#define MyAppVersion "1.0.0"
#define MyAppExe "Naturen Flow 1.0.0.exe"
#define MyAppPublisher "Naturen"

[Setup]
AppId={{A6A8FC9E-2A34-4D7A-9B73-4E50D5A31C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NaturenFlow
DefaultGroupName={#MyAppName}
OutputDir=installer
OutputBaseFilename=Naturen_Flow_{#MyAppVersion}_Update
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "updater.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
