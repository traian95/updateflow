; Inno Setup - Installer pentru Soft_Admin.exe
; Scriptul este in folderul "exe", deci SourcePath este chiar acest folder.

#define MyAppName "Soft Admin"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Naturen"
#define MyAppExeName "Soft_Admin.exe"
#define MySetupName "Soft_Admin_Setup"
#define MySourceDir AddBackslash(SourcePath)

[Setup]
AppId={{57C2B1B4-AE95-4B33-8FA7-52A068B87A22}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Soft Admin
DefaultGroupName=Soft Admin
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename={#MySetupName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifexist "{#MySourceDir}logo.ico"
SetupIconFile={#MySourceDir}logo.ico
#endif

[Languages]
#ifexist "compiler:Languages\Romanian.isl"
Name: "romanian"; MessagesFile: "compiler:Languages\Romanian.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Files]
Source: "{#MySourceDir}Soft_Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "{#MySourceDir}Naturen2.png"
Source: "{#MySourceDir}Naturen2.png"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}logo.ico"
Source: "{#MySourceDir}logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}app_settings.json"
Source: "{#MySourceDir}app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\Soft Admin"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Soft Admin"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Porneste Soft Admin"; Flags: nowait postinstall skipifsilent
