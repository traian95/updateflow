[Setup]
AppName=NaturenFlow
AppVersion=1.0.0
DefaultDirName={autopf}\NaturenFlow
DefaultGroupName=NaturenFlow
; OBLIGATORIU: Cere drepturi de admin pentru instalare și scriere în Program Files
PrivilegesRequired=admin
Compression=lzma
SolidCompression=yes
OutputDir=Output
OutputBaseFilename=NaturenFlow_Setup
; Previne erorile dacă utilizatorul are deja o versiune instalată și deschisă
CloseApplications=yes
RestartApplications=yes

[Files]
; IMPORTANT: Luăm tot ce a generat PyInstaller în folderul dist. 
; Toate modulele noi (elevation.py, utils.py) sunt deja împachetate de PyInstaller în folderul _internal sau în exe.
Source: "dist\NaturenFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; CHEIA SUCCESULUI: Oferă permisiuni de scriere utilizatorului pe folderul de instalare.
; Asta permite updater.exe să suprascrie version.json și restul fișierelor.
Name: "{app}"; Permissions: users-full

[Icons]
Name: "{group}\NaturenFlow"; Filename: "{app}\NaturenFlow.exe"
Name: "{commondesktop}\NaturenFlow"; Filename: "{app}\NaturenFlow.exe"

[UninstallDelete]
; Șterge tot la dezinstalare: log-uri de debug, fișierele noi de update, etc.
Type: filesandordirs; Name: "{app}\*"

[Run]
; Lansează aplicația cu drepturi normale după ce se termină instalarea
Filename: "{app}\NaturenFlow.exe"; Description: "Lansează NaturenFlow"; Flags: nowait postinstall skipifsilent