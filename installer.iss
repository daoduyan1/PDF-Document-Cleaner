#define MyAppName "PDF Document Cleaner"
#define MyAppVersion "1.5.0"
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
VersionInfoDescription=PDF Document Cleaner for PDF normalization
VersionInfoCopyright=Copyright © Đào Duy An - daoduyan.com
VersionInfoProductName=PDF Document Cleaner
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion=1.5.0.0
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

[InstallDelete]
; Remove OCR and Tesseract payloads bundled by Cleaner 1.4.x during upgrade.
Type: filesandordirs; Name: "{app}\OCR"
Type: filesandordirs; Name: "{app}\_internal\tesseract"
Type: filesandordirs; Name: "{app}\tesseract"
Type: files; Name: "{group}\PDF OCR (module riêng).lnk"
Type: files; Name: "{autodesktop}\PDF OCR.lnk"

[Files]
Source: "dist\PDF_Document_Cleaner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"
Name: "{autodesktop}\PDF Document Cleaner"; Filename: "{app}\PDF_Document_Cleaner.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình Desktop"; GroupDescription: "Tùy chọn:"

[Run]
Filename: "{app}\PDF_Document_Cleaner.exe"; Description: "Mở PDF Document Cleaner"; Flags: postinstall nowait skipifsilent
