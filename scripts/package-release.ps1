param(
    [string]$Version,
    [string]$Name = "MDReader"
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
$packageName = "$Name-v$Version-windows-x64"
$staging = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName-unsigned.zip"
$checksumsPath = Join-Path $releaseRoot "SHA256SUMS.txt"
$distApp = Join-Path $Root "dist\$Name"
$distExe = Join-Path $distApp "$Name.exe"

if (-not (Test-Path -LiteralPath $distExe)) {
    throw "Missing built executable: $distExe. Run build.ps1 first."
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
$resolvedReleaseRoot = (Resolve-Path -LiteralPath $releaseRoot).Path.TrimEnd("\")

foreach ($target in @($staging, $zipPath, $checksumsPath)) {
    if (-not (Test-Path -LiteralPath $target)) {
        continue
    }

    $resolved = (Resolve-Path -LiteralPath $target).Path
    $insideReleaseRoot = $resolved.Equals($resolvedReleaseRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($resolvedReleaseRoot + "\", [StringComparison]::OrdinalIgnoreCase)

    if (-not $insideReleaseRoot) {
        throw "Refusing to remove outside release root: $resolved"
    }

    Remove-Item -LiteralPath $target -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $staging | Out-Null
Copy-Item -LiteralPath $distApp -Destination (Join-Path $staging $Name) -Recurse

foreach ($file in @("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "install.ps1", "uninstall.ps1")) {
    $source = Join-Path $Root $file
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $staging
    }
}

$versionInfo = Join-Path $Root "scripts\version-info.txt"
if (Test-Path -LiteralPath $versionInfo) {
    New-Item -ItemType Directory -Force -Path (Join-Path $staging "scripts") | Out-Null
    Copy-Item -LiteralPath $versionInfo -Destination (Join-Path $staging "scripts\version-info.txt")
}

$notes = @"
MD Reader v$Version - Windows x64

Package: $packageName-unsigned.zip
Build type: Production PyInstaller folder build
Signing status: unsigned. Sign MDReader.exe before public release if a code-signing certificate is available.

Run:
  .\$Name\$Name.exe

Install optional Explorer integration:
  PowerShell -ExecutionPolicy Bypass -File .\install.ps1

Uninstall Explorer integration:
  PowerShell -ExecutionPolicy Bypass -File .\uninstall.ps1
"@
Set-Content -LiteralPath (Join-Path $staging "RELEASE_NOTES.txt") -Value $notes -Encoding UTF8

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force

function Get-RelativeToRelease([string]$Path) {
    $full = (Resolve-Path -LiteralPath $Path).Path
    $base = (Resolve-Path -LiteralPath $releaseRoot).Path.TrimEnd("\") + "\"

    if ($full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($base.Length)
    }

    return $full
}

$hashTargets = @(
    $zipPath,
    (Join-Path $staging "$Name\$Name.exe"),
    (Join-Path $staging "install.ps1"),
    (Join-Path $staging "uninstall.ps1")
) | Where-Object { Test-Path -LiteralPath $_ }

$hashLines = foreach ($target in $hashTargets) {
    $hash = Get-FileHash -LiteralPath $target -Algorithm SHA256
    "$($hash.Hash)  $(Get-RelativeToRelease $target)"
}

Set-Content -LiteralPath $checksumsPath -Value $hashLines -Encoding ASCII

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entryNames = @($zip.Entries | ForEach-Object { $_.FullName -replace "/", "\" })
    $requiredEntries = @(
        "$Name\$Name.exe",
        "$Name\_internal\assets\mermaid.min.js",
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "install.ps1",
        "uninstall.ps1",
        "RELEASE_NOTES.txt"
    )

    foreach ($entry in $requiredEntries) {
        if ($entryNames -notcontains $entry) {
            throw "ZIP verification missing: $entry"
        }
    }
}
finally {
    $zip.Dispose()
}

Write-Host "Release root: $releaseRoot"
Write-Host "ZIP: $zipPath"
Write-Host "Checksums: $checksumsPath"
Write-Host "SHA256:"
Get-Content -LiteralPath $checksumsPath
