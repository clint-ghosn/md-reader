#define MyAppName "MD Reader"
#define MyAppPublisher "MD Reader"
#define MyAppExeName "MDReader.exe"
#ifndef MyAppVersion
#define MyAppVersion "0.1.1"
#endif
#ifndef MyAppVersionInfo
#define MyAppVersionInfo "0.1.1.0"
#endif

[Setup]
AppId={{D43F8F56-8C18-4CE1-8D2D-5EFEB7B97C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MD Reader
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release\v{#MyAppVersion}
OutputBaseFilename=MDReader-v{#MyAppVersion}-windows-x64-setup-unsigned
SetupIconFile=..\src\md_reader\assets\mdreader.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
ChangesAssociations=yes
VersionInfoVersion={#MyAppVersionInfo}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "associate_md"; Description: "Register MD Reader for Markdown files"; GroupDescription: "File integration:"; Flags: checkedonce

[Files]
Source: "..\dist\MDReader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MD Reader"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall MD Reader"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MD Reader"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".md"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\.md\OpenWithProgids"; ValueType: none; ValueName: "MDReader.Markdown"; Flags: uninsdeletevalue; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\MDReader.Markdown"; ValueType: string; ValueName: ""; ValueData: "Markdown Document"; Flags: uninsdeletekey; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\MDReader.Markdown"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Markdown Document"; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\MDReader.Markdown\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"",0"; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\MDReader.Markdown\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate_md
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\Classes\Applications\{#MyAppExeName}\Capabilities"; Flags: uninsdeletevalue; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Markdown reader and editor"; Tasks: associate_md
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".md"; ValueData: "MDReader.Markdown"; Tasks: associate_md

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch MD Reader"; Flags: nowait postinstall skipifsilent
