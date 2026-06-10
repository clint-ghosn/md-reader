# Phase 4: Trust And Distribution Codex Runbook

**Codex goal:** Prepare MD Reader for public download with clear release metadata, checksum verification, optional Authenticode signing, and optional winget submission.

**Phase output:** Signed artifacts when a certificate is available, documented unsigned behavior when it is not, complete release notes, and a distribution checklist.

**Repo root:** `D:\Dev\workspace\md-reader`

**Prerequisites:** Phase 3 release automation can produce installer, ZIP, and checksums.

## Technical References

- Microsoft SignTool signs Windows files and requires file digest and timestamp digest options for signing/timestamping. Official docs: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
- Microsoft winget manifests can be created with `wingetcreate new`. Official docs: https://learn.microsoft.com/en-us/windows/package-manager/package/manifest
- The winget repository workflow includes manifest validation before submission. Official docs: https://learn.microsoft.com/en-us/windows/package-manager/package/repository
- GitHub CLI can create and upload release assets. Official docs: https://cli.github.com/manual/gh_release_create

## Execution Rules For Codex

1. Never invent certificate details. If signing secrets or a signing certificate are unavailable, keep artifacts unsigned and document that fact.
2. Never commit private keys, `.pfx` files, certificate passwords, or signing tokens.
3. Public release notes must tell users whether artifacts are signed or unsigned.
4. Do not submit to winget until a stable GitHub release URL exists and the installer has passed Phase 5 QA.

## Step 1: Inspect Release Artifacts

Run:

```powershell
git status --short
$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Get-ChildItem "release\v$version"
Get-Content "release\v$version\SHA256SUMS.txt"
```

Confirm these files exist:

- `release\v<version>\MDReader-v<version>-windows-x64-setup-unsigned.exe`
- `release\v<version>\MDReader-v<version>-windows-x64-unsigned.zip`
- `release\v<version>\SHA256SUMS.txt`

If they do not exist, run Phases 1 through 3.

## Step 2: Add Signing Script

Create:

```text
scripts\sign-release.ps1
```

Use this script:

```powershell
param(
    [string]$Version,
    [string]$CertificateThumbprint,
    [string]$CertificatePath,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

if ([string]::IsNullOrWhiteSpace($Version)) {
    $projectFile = Join-Path $Root "pyproject.toml"
    $match = Select-String -Path $projectFile -Pattern '^version\s*=\s*"([^"]+)"'
    if (-not $match) {
        throw "Could not read version from $projectFile"
    }
    $Version = $match.Matches[0].Groups[1].Value
}

$releaseRoot = Join-Path $Root "release\v$Version"
$unsignedInstaller = Join-Path $releaseRoot "MDReader-v$Version-windows-x64-setup-unsigned.exe"
$signedInstaller = Join-Path $releaseRoot "MDReader-v$Version-windows-x64-setup.exe"

if (-not (Test-Path -LiteralPath $unsignedInstaller)) {
    throw "Missing unsigned installer: $unsignedInstaller"
}

$signtoolCommand = Get-Command signtool.exe -ErrorAction SilentlyContinue
$signtoolPath = if ($signtoolCommand) { $signtoolCommand.Source } else { "" }
if ([string]::IsNullOrWhiteSpace($signtoolPath)) {
    $sdkCandidates = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
        Sort-Object FullName -Descending
    $signtoolPath = ($sdkCandidates | Select-Object -First 1).FullName
}

if ([string]::IsNullOrWhiteSpace($signtoolPath) -or -not (Test-Path -LiteralPath $signtoolPath)) {
    throw "signtool.exe was not found. Install Windows SDK or Visual Studio Build Tools."
}

Copy-Item -LiteralPath $unsignedInstaller -Destination $signedInstaller -Force

if (-not [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    & $signtoolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 /v $signedInstaller
} elseif (-not [string]::IsNullOrWhiteSpace($CertificatePath)) {
    & $signtoolPath sign /f $CertificatePath /fd SHA256 /tr $TimestampUrl /td SHA256 /v $signedInstaller
} else {
    throw "Provide -CertificateThumbprint or -CertificatePath. Do not pass certificate passwords on the command line."
}

if ($LASTEXITCODE -ne 0) {
    throw "signtool sign failed with exit code $LASTEXITCODE"
}

& $signtoolPath verify /pa /v $signedInstaller
if ($LASTEXITCODE -ne 0) {
    throw "signtool verify failed with exit code $LASTEXITCODE"
}

$checksumPath = Join-Path $releaseRoot "SHA256SUMS.txt"
$existing = @()
if (Test-Path -LiteralPath $checksumPath) {
    $existing = Get-Content -LiteralPath $checksumPath | Where-Object {
        $_ -notmatch "MDReader-v$Version-windows-x64-setup\.exe$"
    }
}

$hash = Get-FileHash -LiteralPath $signedInstaller -Algorithm SHA256
$line = "$($hash.Hash)  MDReader-v$Version-windows-x64-setup.exe"
Set-Content -LiteralPath $checksumPath -Value ($existing + $line) -Encoding ASCII

Write-Host "Signed installer: $signedInstaller"
Write-Host "Updated checksums: $checksumPath"
```

This script deliberately avoids accepting a certificate password parameter. If a PFX requires a password, use a secure certificate store or a signing provider workflow instead of exposing the password in shell history.

## Step 3: Document Unsigned Release Behavior

Update `docs\release-notes-template.md` so the notes include this exact section:

```markdown
## Windows trust note

If the installer filename includes `unsigned`, it has not been Authenticode-signed. Windows SmartScreen may show a warning until the project publishes signed builds and develops reputation.

Verify downloads with `SHA256SUMS.txt` before installing.
```

If signed builds are available, adjust release workflow asset names so the signed installer is uploaded as:

```text
MDReader-v<version>-windows-x64-setup.exe
```

Keep the unsigned installer in release storage only if the user wants both signed and unsigned artifacts public.

## Step 4: Add Checksum Verification Instructions

Update `README.md` with:

````markdown
## Verify downloads

After downloading a release asset and `SHA256SUMS.txt`, verify the file hash in PowerShell:

```powershell
Get-FileHash .\MDReader-v0.1.1-windows-x64-setup-unsigned.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

The hash printed by `Get-FileHash` should match the line for the downloaded file.
````

Use the current version from `pyproject.toml` instead of hardcoding `0.1.1` if the project version has changed.

## Step 5: Prepare GitHub Release Metadata

After a release exists, run:

```powershell
gh release view "v$version" --json url,assets,tagName,name
```

Confirm:

- Release tag matches `v<version>`.
- Installer asset exists.
- Portable ZIP asset exists.
- `SHA256SUMS.txt` asset exists.
- Release notes include install and trust notes.

If no release exists, do not proceed to winget. Complete signing and README updates, then return to Phase 3.

## Step 6: Prepare winget Draft Only After Public Release

Do this only after Phase 5 QA passes against the public GitHub release asset.

Install or verify wingetcreate:

```powershell
wingetcreate --version
```

If unavailable, install it using Microsoft-documented instructions for Windows Package Manager Manifest Creator, then rerun the version command.

Create a draft manifest from the public release URL:

```powershell
$release = gh release view "v$version" --json assets --jq '.assets[] | select(.name | test("setup.*\\.exe$")) | .url'
wingetcreate new $release
```

Use these values when prompted:

- Package identifier: `MDReader.MDReader`
- Package name: `MD Reader`
- Publisher: `MD Reader`
- Version: current `pyproject.toml` version
- Installer type: `inno`
- Scope: `user`
- Architecture: `x64`
- License: value from `LICENSE`
- Description: `Windows Markdown reader and editor`

Validate the manifest:

```powershell
winget validate <manifest-directory>
```

Do not submit the manifest until the user explicitly approves. If approved, follow Microsoft repository submission instructions.

## Step 7: Update Distribution Checklist

Create:

```text
docs\launch\distribution-checklist.md
```

Use:

```markdown
# Distribution Checklist

1. Build installer, portable ZIP, and checksums.
2. Sign installer if a certificate is available.
3. Verify signed installer with `signtool verify /pa /v`.
4. Verify checksums with `Get-FileHash`.
5. Publish GitHub release through the release workflow.
6. Download assets from GitHub, not local `release\`.
7. Run Phase 5 clean-machine QA.
8. Update README download link if the repository uses a fixed latest-release URL.
9. Draft winget manifest only after QA passes.
10. Submit winget manifest only after explicit user approval.
```

## Phase Completion Criteria

This phase is complete only when:

- `scripts\sign-release.ps1` exists.
- README documents checksum verification.
- Release notes document signed or unsigned trust behavior.
- Existing release assets were inspected with `gh release view`, or absence of a public release was reported.
- winget was not submitted without explicit approval.

## Completion Report Format

```text
Phase 4 complete.
Verified:
- signing script added: pass
- checksum instructions added: pass
- release trust note added: pass
- release assets inspected: pass | not run because <reason>
- winget draft: created | skipped because <reason>

Changed files:
- scripts\sign-release.ps1
- README.md
- docs\release-notes-template.md
- docs\launch\distribution-checklist.md
```
