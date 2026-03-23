; Inno Setup - Soft Admin (Naturen Flow)
; Ruleaza intai build_all.ps1, apoi deschide acest script si Compile (F9).
; Rezultat: NaturenFlow_Admin_Setup.exe in acelasi folder cu acest fisier (build_installers).

#define MyAppName "Naturen Flow - Admin"
#define MyAppExe "Soft_Admin.exe"
#define MyOutputBase "NaturenFlow_Admin_Setup"

[Setup]
AppName={#MyAppName}
AppVersion=1.0.0
DefaultDirName={autopf}\NaturenFlow\Admin
DefaultGroupName=NaturenFlow Admin
DisableDirPage=no
DisableProgramGroupPage=no
OutputDir=.
OutputBaseFilename={#MyOutputBase}
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExe}
#ifexist "exe\logo.ico"
SetupIconFile=exe\logo.ico
#endif

[Files]
Source: "exe\Soft_Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "exe\Naturen2.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "exe\logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "exe\app_settings.json"
Source: "exe\app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Soft Admin"; Filename: "{app}\{#MyAppExe}"
Name: "{userdesktop}\Soft Admin"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Porneste Soft Admin acum"; Flags: postinstall nowait skipifsilent
