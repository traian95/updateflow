; Inno Setup - Installer pentru Soft_Admin.exe
; Compileaza acest fisier in Inno Setup (F9).

#define MyAppName "Soft Admin"
#define MyAppVersion "1.0.0"
#define MyAppExeName "Soft_Admin.exe"
#define MySetupName "Soft_Admin_Setup"
#define MySourceDir AddBackslash(SourcePath) + "exe"

[Setup]
AppId={{57C2B1B4-AE95-4B33-8FA7-52A068B87A22}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Soft Admin
DefaultGroupName=Soft Admin
OutputDir=.
OutputBaseFilename={#MySetupName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifexist "{#MySourceDir}\logo.ico"
SetupIconFile={#MySourceDir}\logo.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Files]
Source: "{#MySourceDir}\Soft_Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "{#MySourceDir}\Naturen2.png"
Source: "{#MySourceDir}\Naturen2.png"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}\logo.ico"
Source: "{#MySourceDir}\logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}\app_settings.json"
Source: "{#MySourceDir}\app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Soft Admin"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\Soft Admin"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Porneste Soft Admin"; Flags: nowait postinstall skipifsilent
