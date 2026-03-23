; Inno Setup - Installer pentru Soft_Ofertare.exe
; Scriptul este in folderul "exe", deci SourcePath este chiar acest folder.

#define MyAppName "Soft Ofertare"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Naturen"
#define MyAppExeName "Soft_Ofertare.exe"
#define MySetupName "Soft_Ofertare_Setup"
#define MySourceDir AddBackslash(SourcePath)

[Setup]
AppId={{8A4A5F9D-5A9F-4FA5-8D19-0A3A83D28001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Soft Ofertare
DefaultGroupName=Soft Ofertare
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename={#MySetupName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
#ifexist "{#MySourceDir}logo.ico"
SetupIconFile={#MySourceDir}logo.ico
#endif

[Languages]
#ifexist "compiler:Languages\Romanian.isl"
Name: "romanian"; MessagesFile: "compiler:Languages\Romanian.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Creeaza scurtatura pe Desktop"; GroupDescription: "Optiuni:"

[Files]
Source: "{#MySourceDir}Soft_Ofertare.exe"; DestDir: "{app}"; Flags: ignoreversion
#ifexist "{#MySourceDir}Naturen2.png"
Source: "{#MySourceDir}Naturen2.png"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}logo.ico"
Source: "{#MySourceDir}logo.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif
#ifexist "{#MySourceDir}app_settings.json"
Source: "{#MySourceDir}app_settings.json"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\Soft Ofertare"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Soft Ofertare"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Porneste Soft Ofertare"; Flags: nowait postinstall skipifsilent
