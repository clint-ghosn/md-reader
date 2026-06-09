# Phase 2: Installer Codex Runbook

**Codex goal:** Add a Windows installer so MD Reader can be downloaded, installed, launched from Start, associated with Markdown files, and uninstalled cleanly.

**Phase output:** An Inno Setup script, a build helper for the installer, and a verified installer EXE in the release folder.

**Repo root:** `D:\Dev\workspace\md-reader`

**Prerequisite:** Phase 1 must already produce a working `dist\MDReader\MDReader.exe`.

## Technical References

- Inno Setup `PrivilegesRequired=lowest` keeps the installer in non-administrative install mode. Official docs: https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm
- Inno Setup registry entries can create file associations, and uninstall cleanup requires explicit `uninsdelete*` flags. Official docs: https://jrsoftware.org/ishelp/topic_registrysection.htm
- Inno Setup FAQ documents `ChangesAssociations=yes` and file association patterns. Official docs: https://jrsoftware.org/isfaq.php
- The Inno Setup command-line compiler supports `/DName=Value` preprocessor defines. Official docs: https://jrsoftware.org/is6help/topic_isppcc.htm

## Execution Rules For Codex

1. Do not rewrite app code in this phase unless the installer exposes a launch failure.
2. Use per-user installation by default so users do not need admin rights.
3. Use `installer\MDReader.iss` as the canonical installer script.
4. Use `scripts\build-installer.ps1` as the canonical installer build command.
5. Keep `install.ps1` and `uninstall.ps1` as portable-ZIP fallback scripts unless the user asks to remove them.

## Step 1: Inspect Baseline State

Run:

```powershell
git status --short
Test-Path dist\MDReader\MDReader.exe
Get-Content pyproject.toml
Get-Content src\md_reader\__init__.py
Get-Content build.ps1
Get-Content scripts\package-release.ps1
Get-Content install.ps1
Get-Content uninstall.ps1
```

If `dist\MDReader\MDReader.exe` is missing, run Phase 1 first:

```powershell
.\build.ps1
.\scripts\package-release.ps1
```

## Step 2: Create The Installer Directory

Create:

```text
installer\MDReader.iss
```

Use this Inno Setup script as the baseline. Keep the `AppId` value stable after the first public release.

```ini
#define MyAppName "MD Reader"
#define MyAppPublisher "MD Reader"
#define MyAppExeName "MDReader.exe"
#define MyAppInternalName "MDReader"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#ifndef MyAppVersionInfo
#define MyAppVersionInfo "0.1.0.0"
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
```

The installer registers MD Reader as an available Markdown opener. Do not force-edit Windows `UserChoice`; Windows protects that key and forced writes are brittle.

## Step 3: Add Installer Build Helper

Create:

```text
scripts\build-installer.ps1
```

Use this script:

```powershell
param(
    [string]$Version,
    [string]$InnoCompilerPath
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistExe = Join-Path $Root "dist\MDReader\MDReader.exe"
$InstallerScript = Join-Path $Root "installer\MDReader.iss"

if ([string]::IsNullOrWhiteSpace($Version)) {
    $projectFile = Join-Path $Root "pyproject.toml"
    $match = Select-String -Path $projectFile -Pattern '^version\s*=\s*"([^"]+)"'
    if (-not $match) {
        throw "Could not read version from $projectFile"
    }
    $Version = $match.Matches[0].Groups[1].Value
}

if (-not (Test-Path -LiteralPath $DistExe)) {
    throw "Missing built executable: $DistExe. Run build.ps1 first."
}

if (-not (Test-Path -LiteralPath $InstallerScript)) {
    throw "Missing installer script: $InstallerScript"
}

if ([string]::IsNullOrWhiteSpace($InnoCompilerPath)) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    $InnoCompilerPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if ([string]::IsNullOrWhiteSpace($InnoCompilerPath) -or -not (Test-Path -LiteralPath $InnoCompilerPath)) {
    throw "Could not find ISCC.exe. Install Inno Setup 6 or pass -InnoCompilerPath."
}

$versionParts = $Version.Split(".")
if ($versionParts.Count -eq 3) {
    $VersionInfo = "$Version.0"
} else {
    $VersionInfo = $Version
}

& $InnoCompilerPath "/DMyAppVersion=$Version" "/DMyAppVersionInfo=$VersionInfo" $InstallerScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
}

$installer = Join-Path $Root "release\v$Version\MDReader-v$Version-windows-x64-setup-unsigned.exe"
if (-not (Test-Path -LiteralPath $installer)) {
    throw "Installer was not created at expected path: $installer"
}

Write-Host "Installer: $installer"
```

## Step 4: Update Release Packaging

Modify `scripts\package-release.ps1` so it includes installer artifacts when they exist.

Add the installer path after `$checksumsPath` is defined:

```powershell
$installerPath = Join-Path $releaseRoot "$Name-v$Version-windows-x64-setup-unsigned.exe"
```

Add `$installerPath` to `$hashTargets` only if it exists:

```powershell
$hashTargets = @(
    $zipPath,
    $installerPath,
    (Join-Path $staging "$Name\$Name.exe"),
    (Join-Path $staging "install.ps1"),
    (Join-Path $staging "uninstall.ps1")
) | Where-Object { Test-Path -LiteralPath $_ }
```

Do not make `package-release.ps1` fail if the installer has not been built yet. Phase 3 will control CI ordering.

## Step 5: Update README Install Instructions

Update `README.md` with two install paths:

```markdown
## Download and install

For normal use, download `MDReader-v0.1.0-windows-x64-setup-unsigned.exe` from the latest GitHub release and run it.

For portable use, download `MDReader-v0.1.0-windows-x64-unsigned.zip`, extract it, and run `MDReader\MDReader.exe`.

The installer registers MD Reader as an available Markdown opener for the current Windows user. If Windows keeps another default app for `.md` files, choose MD Reader from **Settings > Apps > Default apps**.
```

Use the actual current version from `pyproject.toml`.

## Step 6: Build And Verify The Installer

Run:

```powershell
.\build.ps1
.\scripts\build-installer.ps1
.\scripts\package-release.ps1
```

Expected artifacts:

```powershell
Test-Path release\v0.1.0\MDReader-v0.1.0-windows-x64-setup-unsigned.exe
Test-Path release\v0.1.0\MDReader-v0.1.0-windows-x64-unsigned.zip
Test-Path release\v0.1.0\SHA256SUMS.txt
```

All commands must print `True`.

## Step 7: Silent Install Smoke Test

Run this only if Windows GUI execution is available:

```powershell
$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$installer = Resolve-Path "release\v$version\MDReader-v$version-windows-x64-setup-unsigned.exe"
$installDir = Join-Path $env:LOCALAPPDATA "Programs\MD Reader"
Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
if (-not (Test-Path -LiteralPath (Join-Path $installDir "MDReader.exe"))) { throw "Installed EXE missing" }
Start-Process -FilePath (Join-Path $installDir "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
```

If this test cannot run in the current environment, state that explicitly in the completion report.

## Phase Completion Criteria

This phase is complete only when:

- `installer\MDReader.iss` exists.
- `scripts\build-installer.ps1` exists.
- `.\scripts\build-installer.ps1` produces the installer EXE.
- `scripts\package-release.ps1` includes the installer checksum when the installer exists.
- README documents installer and portable ZIP install paths.
- Silent install/uninstall was run, or the environment limitation was reported.

## Completion Report Format

```text
Phase 2 complete.
Verified:
- build.ps1: pass
- build-installer.ps1: pass
- package-release.ps1: pass
- silent install/uninstall: pass | not run because <reason>

Changed files:
- installer\MDReader.iss
- scripts\build-installer.ps1
- scripts\package-release.ps1
- README.md

Installer artifact:
- <actual installer path>
```
