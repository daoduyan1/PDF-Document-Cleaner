
#define MyAppName "PDF Document Cleaner"
#define MyAppVersion "1.0.1"

[Setup]
AppId={{C29E23F2-90D7-4B62-9E70-9B26B2B8B341}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\PDF Document Cleaner
DefaultGroupName=PDF Document Cleaner
OutputDir=dist
OutputBaseFilename=PDF_Document_Cleaner_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Files]
Source: "dist\PDF_Document_Cleaner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"
Name: "{autodesktop}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"

[Run]
Filename: "{app}\PDF_Document_Cleaner.exe"; Description: "Mở PDF Document Cleaner"; Flags: postinstall nowait skipifsilent
