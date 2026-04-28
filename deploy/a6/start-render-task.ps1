$ErrorActionPreference = "Stop"

$taskName = "Abu Dhabi E-Ink Render Publisher"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
