; Inno Setup script pentru Soft Ofertare (aplicația principală)

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

[Files]
; Copiem structura pregătită în folderul release\run_ofertare
Source: "release\run_ofertare\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
; Meniu Start
Name: "{group}\Soft Ofertare"; Filename: "{app}\run_ofertare.exe"

; Scurtătură pe Desktop (opțională)
Name: "{userdesktop}\Soft Ofertare"; Filename: "{app}\run_ofertare.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creează scurtătură pe Desktop"; GroupDescription: "Opțiuni suplimentare:"

[Run]
; Pornește Soft Ofertare după instalare
Filename: "{app}\run_ofertare.exe"; Description: "Pornește Soft Ofertare acum"; Flags: postinstall nowait skipifsilent

