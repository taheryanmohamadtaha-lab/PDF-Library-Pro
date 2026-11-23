#define MyAppName "PDF Library Pro"
#define MyAppVersion "1.0.0"
#define MyAppExe "PDFLibraryPro.exe"

[Setup]
AppId={{6B1B1B7E-5D3A-4B7C-9D0E-0A1B2C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\PDFLibraryPro
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=PDFLibraryPro-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\app\resources\app.ico
UninstallDisplayIcon={app}\{#MyAppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; User data lives in %APPDATA%\PDFLibraryPro and is intentionally NOT removed on uninstall.
