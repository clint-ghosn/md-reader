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
    $sdkRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path -LiteralPath $sdkRoot) {
        $sdkCandidates = Get-ChildItem $sdkRoot -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending
        $signtoolPath = ($sdkCandidates | Select-Object -First 1).FullName
    }
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
