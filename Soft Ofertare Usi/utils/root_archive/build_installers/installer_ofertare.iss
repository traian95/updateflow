; Inno Setup - Soft Ofertare (Naturen Flow)
; IMPORTANT: Ruleaza intai build_all.ps1 din radacina proiectului, apoi deschide acest script.
; Inno Setup: File -> Open -> alegi acest fisier. Asigura-te ca esti in folderul build_installers (cd build_installers) cand rulezi iscc.

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
#ifexist "exe\logo.ico"
SetupIconFile=exe\logo.ico
#endif

[Files]
Source: "exe\Soft_Ofertare.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "exe\Naturen2.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "exe\logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "exe\app_settings.json"
Source: "exe\app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Soft Ofertare"; Filename: "{app}\{#MyAppExe}"
Name: "{userdesktop}\Soft Ofertare"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Porneste Soft Ofertare acum"; Flags: postinstall nowait skipifsilent
