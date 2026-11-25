#define MyAppName "PDF Document Cleaner"
#define MyAppVersion "1.3.2"
#define MyAppPublisher "HMDS"
#define MyAppURL "https://hmds.vn"

[Setup]
AppId={{C29E23F2-90D7-4B62-9E70-9B26B2B8B341}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright © Đào Duy An - daoduyan.com
VersionInfoCompany=HMDS
VersionInfoDescription=PDF Document Cleaner and separate Vietnamese OCR module
VersionInfoCopyright=Copyright © Đào Duy An - daoduyan.com
VersionInfoProductName=PDF Document Cleaner
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion=1.3.2.0
VersionInfoOriginalFileName=PDF_Document_Cleaner.exe
DefaultDirName={autopf}\PDF Document Cleaner
DefaultGroupName=PDF Document Cleaner
UninstallDisplayIcon={app}\PDF_Document_Cleaner.exe
OutputDir=dist
OutputBaseFilename=PDF_Document_Cleaner_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Files]
Source: "dist\PDF_Document_Cleaner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\OCR_Package\*"; DestDir: "{app}\OCR"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"
Name: "{autodesktop}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"; Tasks: desktopicon
Name: "{group}\PDF OCR (module riêng)"; Filename: "{app}\OCR\PDF_OCR.exe"
Name: "{autodesktop}\PDF OCR"; Filename: "{app}\OCR\PDF_OCR.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình Desktop"; GroupDescription: "Tùy chọn:"

[Run]
Filename: "{app}\PDF_Document_Cleaner.exe"; Description: "Mở PDF Document Cleaner"; Flags: postinstall nowait skipifsilent
