# Phase 5: Clean-Machine QA Codex Runbook

**Codex goal:** Verify that public MD Reader artifacts are downloadable, installable, executable, uninstallable, and usable on clean Windows machines.

**Phase output:** A completed QA report with pass/fail evidence for installer, portable ZIP, file association, launch, core workflows, uninstall, and reinstall.

**Repo root:** `D:\Dev\workspace\md-reader`

**Prerequisites:** Phase 3 release automation has published assets, and Phase 4 trust/distribution metadata is in place.

## Execution Rules For Codex

1. Test downloaded GitHub release assets, not local build outputs.
2. Use at least one clean Windows 11 environment. Use Windows 10 as a second environment when available.
3. Do not skip uninstall/reinstall tests.
4. Record exact OS version, artifact names, checksums, and failures.
5. If a GUI cannot be automated in the current environment, produce the QA report with blocked GUI steps clearly marked.

## Step 1: Create QA Report File

Create:

```text
docs\launch\qa-report-v0.1.1.md
```

Use the actual current version from `pyproject.toml` in the filename.

Start with:

```markdown
# MD Reader v0.1.1 Clean-Machine QA Report

**Release tag:** v0.1.1
**QA date:** 2026-06-08
**Tester:** Codex
**Artifacts source:** GitHub Release

## Environments

| Environment | OS build | Architecture | Account type | Result |
| --- | --- | --- | --- | --- |
| Windows 11 clean VM |  | x64 | standard user | Not started |
| Windows 10 clean VM |  | x64 | standard user | Not started |

## Artifacts

| File | SHA256 | Result |
| --- | --- | --- |
| MDReader-v0.1.1-windows-x64-setup-unsigned.exe |  | Not started |
| MDReader-v0.1.1-windows-x64-unsigned.zip |  | Not started |
| SHA256SUMS.txt |  | Not started |
```

Replace `0.1.1` with the actual version before saving.

## Step 2: Download Public Release Assets

Run:

```powershell
$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$tag = "v$version"
$downloadRoot = Join-Path $env:TEMP "mdreader-qa-$version"
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
gh release download $tag --dir $downloadRoot --pattern "MDReader-v$version-windows-x64-setup*.exe"
gh release download $tag --dir $downloadRoot --pattern "MDReader-v$version-windows-x64-unsigned.zip"
gh release download $tag --dir $downloadRoot --pattern "SHA256SUMS.txt"
Get-ChildItem $downloadRoot
```

If GitHub CLI is unavailable, download the same three assets from the release page in a browser and place them under:

```text
%TEMP%\mdreader-qa-<version>
```

## Step 3: Verify Checksums

Run:

```powershell
Get-Content "$downloadRoot\SHA256SUMS.txt"
Get-FileHash "$downloadRoot\MDReader-v$version-windows-x64-setup-unsigned.exe" -Algorithm SHA256
Get-FileHash "$downloadRoot\MDReader-v$version-windows-x64-unsigned.zip" -Algorithm SHA256
```

If the installer is signed and does not include `unsigned`, adjust the filename to:

```text
MDReader-v<version>-windows-x64-setup.exe
```

Record the hash values in the QA report.

## Step 4: Capture Environment Details

Run on each clean test machine:

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture
whoami
```

Record:

- Windows product name
- Windows version
- OS build number
- architecture
- whether the account is a standard user or administrator

## Step 5: Test Installer Install

Run:

```powershell
$installer = Get-ChildItem $downloadRoot -Filter "MDReader-v$version-windows-x64-setup*.exe" | Select-Object -First 1
Start-Process -FilePath $installer.FullName -Wait
```

Manual checks:

- Installer opens without missing-runtime errors.
- Default install path is under `%LOCALAPPDATA%\Programs\MD Reader`.
- User can complete install without admin elevation.
- Start menu shortcut appears.
- Optional launch-on-finish starts MD Reader.

Record pass/fail in the QA report.

## Step 6: Test Executable Launch

Run:

```powershell
$installedExe = Join-Path $env:LOCALAPPDATA "Programs\MD Reader\MDReader.exe"
Test-Path $installedExe
Start-Process -FilePath $installedExe
```

Manual checks:

- Main window opens.
- No console window appears.
- Icon appears in the window and taskbar.
- App remains open for at least 30 seconds.

Record pass/fail.

## Step 7: Test Core App Workflows

Create a test Markdown file:

````powershell
$sample = Join-Path $env:TEMP "mdreader-sample.md"
@"
# MD Reader QA

This is a **bold** test.

```mermaid
graph TD
  A-->B
```
"@ | Set-Content -LiteralPath $sample -Encoding UTF8
````

Manual workflow checks:

- Open the sample file from `File > Open`.
- Preview renders heading, bold text, and Mermaid diagram.
- Switch between preview, raw, and split modes if those controls are available.
- Edit the file and save.
- Use `File > Export HTML`.
- Open the exported HTML and confirm content is present.
- Close and reopen MD Reader; recent files and layout settings should persist.

Record pass/fail and attach brief notes for any visual or rendering issue.

## Step 8: Test Markdown File Association

Run:

```powershell
Get-ItemProperty "HKCU:\Software\Classes\.md\OpenWithProgids" -ErrorAction SilentlyContinue
Get-ItemProperty "HKCU:\Software\Classes\MDReader.Markdown\shell\open\command" -ErrorAction SilentlyContinue
```

Manual checks:

- Right-click the sample `.md` file.
- Confirm MD Reader appears under Open With.
- If MD Reader is the default `.md` app, double-click opens the file in MD Reader.
- If Windows keeps another default, use Settings > Apps > Default apps and verify MD Reader is selectable for `.md`.

Record the exact behavior. Do not mark the test failed solely because Windows preserved a previous default app, as long as MD Reader is registered as an available opener.

## Step 9: Test Portable ZIP

Run:

```powershell
$portableRoot = Join-Path $env:TEMP "mdreader-portable-$version"
Expand-Archive -LiteralPath "$downloadRoot\MDReader-v$version-windows-x64-unsigned.zip" -DestinationPath $portableRoot -Force
Test-Path "$portableRoot\MDReader\MDReader.exe"
Start-Process -FilePath "$portableRoot\MDReader\MDReader.exe"
```

Manual checks:

- Portable app launches without installer.
- Mermaid preview works.
- `install.ps1` and `uninstall.ps1` exist in the portable package if portable Explorer integration is still supported.

Record pass/fail.

## Step 10: Test Uninstall

Run:

```powershell
$uninstaller = Join-Path $env:LOCALAPPDATA "Programs\MD Reader\unins000.exe"
Test-Path $uninstaller
Start-Process -FilePath $uninstaller -Wait
```

Manual checks:

- Uninstaller completes without admin elevation.
- Start menu shortcut is removed.
- `%LOCALAPPDATA%\Programs\MD Reader\MDReader.exe` is removed.
- MD Reader-specific registry keys are removed or no longer point to the uninstalled path.

Registry checks:

```powershell
Test-Path "HKCU:\Software\Classes\MDReader.Markdown"
Test-Path "HKCU:\Software\Classes\Applications\MDReader.exe"
```

Record pass/fail.

## Step 11: Test Reinstall Over Previous Install

Run the installer again:

```powershell
Start-Process -FilePath $installer.FullName -Wait
Test-Path (Join-Path $env:LOCALAPPDATA "Programs\MD Reader\MDReader.exe")
```

Manual checks:

- Reinstall completes.
- App launches.
- Existing user settings do not prevent launch.

Record pass/fail.

## Step 12: Complete QA Report

Add this summary table to the QA report:

```markdown
## Test Results

| Test | Windows 11 | Windows 10 | Notes |
| --- | --- | --- | --- |
| Download release assets |  |  |  |
| Verify checksums |  |  |  |
| Installer launches |  |  |  |
| Installs without admin |  |  |  |
| Start menu launch |  |  |  |
| Main app launch |  |  |  |
| Open Markdown file |  |  |  |
| Mermaid preview |  |  |  |
| Edit and save |  |  |  |
| Export HTML |  |  |  |
| Open With registration |  |  |  |
| Double-click `.md` behavior |  |  |  |
| Portable ZIP launch |  |  |  |
| Uninstall |  |  |  |
| Reinstall |  |  |  |

## Final Decision

Release status: Pass | Fail

Blocking issues:

- None

Non-blocking issues:

- None
```

Replace `Pass | Fail` with exactly one status.

## Phase Completion Criteria

This phase is complete only when:

- Public release assets were downloaded.
- Checksums were verified.
- Installer install, launch, uninstall, and reinstall were tested.
- Portable ZIP launch was tested.
- Markdown file association was inspected.
- QA report contains environment details and final decision.

## Completion Report Format

```text
Phase 5 complete.
Verified:
- release download: pass
- checksum verification: pass
- installer install: pass
- app launch: pass
- portable launch: pass
- uninstall/reinstall: pass

QA report:
- docs\launch\qa-report-v<version>.md

Release decision:
- pass | fail
```
