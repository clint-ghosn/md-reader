param(
    [string]$Name = "MDReader"
)

$ErrorActionPreference = "Stop"
$DistRoot = Join-Path $PSScriptRoot "dist\$Name"

function Get-MDReaderRunningProcesses {
    if (-not (Test-Path -LiteralPath $DistRoot)) {
        return @()
    }

    $resolvedDistRoot = (Resolve-Path -LiteralPath $DistRoot).Path
    return @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.ExecutablePath -and
                ($_.ExecutablePath -eq (Join-Path $resolvedDistRoot "$Name.exe") -or
                    $_.ExecutablePath.StartsWith($resolvedDistRoot, [System.StringComparison]::OrdinalIgnoreCase))
            } |
            Select-Object Name, ProcessId, ExecutablePath
    )
}

function Assert-MDReaderNotRunning {
    $runningProcesses = Get-MDReaderRunningProcesses
    if ($runningProcesses.Count -eq 0) {
        return
    }

    $details = ($runningProcesses | ForEach-Object {
        "PID $($_.ProcessId): $($_.Name) - $($_.ExecutablePath)"
    }) -join [Environment]::NewLine
    throw "MD Reader is still running from $DistRoot. Close these processes before rebuilding:$([Environment]::NewLine)$details"
}

function Remove-MDReaderCache {
    $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        Write-Warning "LOCALAPPDATA is unavailable; skipping MDReader cache cleanup."
        return
    }

    $cachePaths = @(
        # Current Qt cache location after setting the MDReader application identity.
        (Join-Path $localAppData "MDReader\MD Reader\cache\WebEngine"),
        (Join-Path $localAppData "MDReader\MD Reader\cache\http_cache"),
        (Join-Path $localAppData "MDReader\MD Reader\cache\GPUCache"),
        # Previous app-specific fallback location.
        (Join-Path $localAppData "MDReader\MD Reader\WebEngine"),
        (Join-Path $localAppData "MDReader\MD Reader\http_cache"),
        (Join-Path $localAppData "MDReader\MD Reader\GPUCache"),
        # Legacy Qt path used before the app configured its identity.
        (Join-Path $localAppData "cache\WebEngine"),
        (Join-Path $localAppData "cache\http_cache"),
        (Join-Path $localAppData "cache\GPUCache")
    ) | Select-Object -Unique

    foreach ($path in $cachePaths) {
        if (Test-Path -LiteralPath $path) {
            try {
                Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
                Write-Host "Cleared cache $path"
            } catch {
                Write-Warning "Could not clear cache $path. Close MD Reader and rebuild again. $($_.Exception.Message)"
            }
        }
    }
}

Assert-MDReaderNotRunning
Remove-MDReaderCache

.\scripts\make-icon.ps1

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $Name `
    --paths "src" `
    --icon "src\md_reader\assets\mdreader.ico" `
    --version-file "scripts\version-info.txt" `
    --add-data "src\md_reader\assets\mdreader.ico;assets" `
    --add-data "src\md_reader\assets\mermaid.min.js;assets" `
    --add-data "src\md_reader\assets\mermaid.LICENSE.txt;assets" `
    --hidden-import PySide6.QtWebEngineWidgets `
    --hidden-import PySide6.QtWebEngineCore `
    --hidden-import PySide6.QtWebEngineQuick `
    "src\md_reader\__main__.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Remove-MDReaderCache

Write-Host "Built dist\$Name\$Name.exe"
