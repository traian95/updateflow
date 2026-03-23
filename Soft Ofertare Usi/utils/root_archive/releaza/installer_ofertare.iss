; Inno Setup – Soft Ofertare (rulează din folderul releaza)
; Conținut: run_ofertare\* (exe, db, logo, ico, app_settings.json)

[Setup]
AppName=Naturen Flow - Ofertare
AppVersion=1.0.0
DefaultDirName={pf}\NaturenFlow\Ofertare
DefaultGroupName=NaturenFlow Ofertare
DisableDirPage=no
DisableProgramGroupPage=no
OutputDir=.
OutputBaseFilename=NaturenFlow_Ofertare_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=run_ofertare\logo.ico
UninstallDisplayIcon={app}\logo.ico

[Files]
Source: "run_ofertare\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Soft Ofertare"; Filename: "{app}\run_ofertare.exe"
Name: "{userdesktop}\Soft Ofertare"; Filename: "{app}\run_ofertare.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creează scurtătură pe Desktop"; GroupDescription: "Opțiuni suplimentare:"

[Run]
Filename: "{app}\run_ofertare.exe"; Description: "Pornește Soft Ofertare acum"; Flags: postinstall nowait skipifsilent
