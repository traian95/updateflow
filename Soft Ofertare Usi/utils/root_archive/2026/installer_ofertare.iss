; Inno Setup - Soft Ofertare (Naturen Flow)
; Ruleaza build_all.ps1 inainte (daca vrei sa regenerezi exe),
; apoi compilezi acest .iss in Inno Setup.

#define MyAppName "Naturen Flow - Ofertare"
#define MyAppExe "Soft_Ofertare.exe"
#define MyOutputBase "NaturenFlow_Ofertare_Setup"

[Setup]
AppName={#MyAppName}
AppVersion=1.0.0
DefaultDirName={autopf}\NaturenFlow\Ofertare
DefaultGroupName=NaturenFlow Ofertare
DisableDirPage=no
DisableProgramGroupPage=no
OutputDir=.
OutputBaseFilename={#MyOutputBase}
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExe}
SetupIconFile=logo.ico

[Files]
Source: "Soft_Ofertare.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "Naturen1.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "app_settings.json"
Source: "app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Soft Ofertare"; Filename: "{app}\{#MyAppExe}"
Name: "{userdesktop}\Soft Ofertare"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Porneste Soft Ofertare acum"; Flags: postinstall nowait skipifsilent

