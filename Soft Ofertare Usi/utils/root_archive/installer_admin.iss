; Inno Setup script pentru Soft Admin (aplicația de administrare)

[Setup]
AppName=Naturen Flow - Admin
AppVersion=1.0.0
DefaultDirName={pf}\NaturenFlow\Admin
DefaultGroupName=NaturenFlow Admin
DisableDirPage=no
DisableProgramGroupPage=no
OutputDir=.
OutputBaseFilename=NaturenFlow_Admin_Setup
Compression=lzma
SolidCompression=yes

[Files]
; Copiem structura pregătită în folderul release\admin_app
Source: "release\admin_app\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
; Meniu Start
Name: "{group}\Soft Admin"; Filename: "{app}\admin_app.exe"

; Scurtătură pe Desktop (opțională)
Name: "{userdesktop}\Soft Admin"; Filename: "{app}\admin_app.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creează scurtătură pe Desktop"; GroupDescription: "Opțiuni suplimentare:"

[Run]
; Pornește Soft Admin după instalare
Filename: "{app}\admin_app.exe"; Description: "Pornește Soft Admin acum"; Flags: postinstall nowait skipifsilent

