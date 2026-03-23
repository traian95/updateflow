; Inno Setup - Soft Admin (Naturen Flow)
; Ruleaza build_all.ps1 inainte (daca vrei sa regenerezi exe),
; apoi compilezi acest .iss in Inno Setup.

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
SetupIconFile=logo.ico

[Files]
Source: "Soft_Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "Naturen1.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "app_settings.json"
Source: "app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Soft Admin"; Filename: "{app}\{#MyAppExe}"
Name: "{userdesktop}\Soft Admin"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Porneste Soft Admin acum"; Flags: postinstall nowait skipifsilent

