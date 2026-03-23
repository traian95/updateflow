; Inno Setup – Soft Admin (rulează din folderul releaza)
; Conținut: admin_app\* (exe, db, logo, ico, app_settings.json)

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
SetupIconFile=admin_app\logo.ico
UninstallDisplayIcon={app}\logo.ico

[Files]
Source: "admin_app\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Soft Admin"; Filename: "{app}\admin_app.exe"
Name: "{userdesktop}\Soft Admin"; Filename: "{app}\admin_app.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Creează scurtătură pe Desktop"; GroupDescription: "Opțiuni suplimentare:"

[Run]
Filename: "{app}\admin_app.exe"; Description: "Pornește Soft Admin acum"; Flags: postinstall nowait skipifsilent
