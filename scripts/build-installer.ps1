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
