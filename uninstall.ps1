$ErrorActionPreference = "Stop"

$classes = "HKCU:\Software\Classes"
$progId = "MDReader.Markdown"
$mdKey = "$classes\.md"
$openWithKey = "$mdKey\OpenWithProgids"

if (Test-Path -LiteralPath $openWithKey) {
    Remove-ItemProperty -Path $openWithKey -Name $progId -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $mdKey) {
    $defaultValue = (Get-Item -LiteralPath $mdKey).GetValue("")
    if ($defaultValue -eq $progId) {
        Set-Item -Path $mdKey -Value ""
    }
}

Remove-Item -Path "$classes\$progId" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$classes\Applications\MDReader.exe" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Removed MD Reader per-user registration."
