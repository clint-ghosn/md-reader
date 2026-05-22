param(
    [string]$ExePath = "$PSScriptRoot\dist\MDReader\MDReader.exe"
)

$ErrorActionPreference = "Stop"

$resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
$classes = "HKCU:\Software\Classes"
$progId = "MDReader.Markdown"
$appKey = "$classes\Applications\MDReader.exe"
$capabilitiesKey = "$appKey\Capabilities"

New-Item -Path "$classes\.md" -Force | Out-Null
New-Item -Path "$classes\.md\OpenWithProgids" -Force | Out-Null
Set-ItemProperty -Path "$classes\.md\OpenWithProgids" -Name $progId -Value ([byte[]]@()) -Type Binary
Set-Item -Path "$classes\.md" -Value $progId
Set-ItemProperty -Path "$classes\.md" -Name "Content Type" -Value "text/markdown"
Set-ItemProperty -Path "$classes\.md" -Name "PerceivedType" -Value "text"

New-Item -Path "$classes\$progId\shell\open\command" -Force | Out-Null
New-Item -Path "$classes\$progId\DefaultIcon" -Force | Out-Null
Set-Item -Path "$classes\$progId" -Value "Markdown Document"
Set-ItemProperty -Path "$classes\$progId" -Name "FriendlyTypeName" -Value "Markdown Document"
Set-Item -Path "$classes\$progId\DefaultIcon" -Value "`"$resolvedExe`",0"
Set-Item -Path "$classes\$progId\shell\open\command" -Value "`"$resolvedExe`" `"%1`""

New-Item -Path "$capabilitiesKey\FileAssociations" -Force | Out-Null
Set-ItemProperty -Path "$capabilitiesKey" -Name "ApplicationName" -Value "MD Reader"
Set-ItemProperty -Path "$capabilitiesKey" -Name "ApplicationDescription" -Value "Markdown reader and editor"
Set-ItemProperty -Path "$capabilitiesKey\FileAssociations" -Name ".md" -Value $progId

Write-Host ".md files are now associated with $resolvedExe for the current user."
Write-Host "Explorer may need to be restarted before the association is visible."
Write-Host "Formatted Explorer preview requires a registered COM IPreviewHandler CLSID."
