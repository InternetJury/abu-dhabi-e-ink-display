param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$TaskName = "Abu Dhabi E-Ink Render Publisher",
    [int]$MaxFrameAgeSeconds = 90,
    [int]$MaxLogAgeSeconds = 90,
    [int]$LogRetentionDays = 14
)

$ErrorActionPreference = "Stop"

$framesDir = Join-Path $InstallRoot "frames"
$logsDir = Join-Path $InstallRoot "logs"
$currentFrame = Join-Path $framesDir "current.png"
$publishHealthFile = Join-Path $logsDir "last-successful-publish.txt"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Get-ChildItem -Path $logsDir -Filter "publisher-watchdog-*.log" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1 * $LogRetentionDays) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

function Write-WatchdogLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    $logPath = Join-Path $logsDir ("publisher-watchdog-" + (Get-Date -Format "yyyyMMdd") + ".log")
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

function Get-PublisherTaskStatus {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
    }
    catch {
        return [pscustomobject]@{
            IsRunning = $false
            RunAgeSeconds = [double]::PositiveInfinity
        }
    }
    return [pscustomobject]@{
        IsRunning = $task.State -eq "Running"
        RunAgeSeconds = ((Get-Date) - $taskInfo.LastRunTime).TotalSeconds
    }
}

function Get-FileAgeSeconds {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [double]::PositiveInfinity
    }
    return ((Get-Date) - (Get-Item -LiteralPath $Path).LastWriteTime).TotalSeconds
}

function Get-LatestPublisherLogAgeSeconds {
    $latestLog = Get-ChildItem -Path $logsDir -Filter "render-publisher-*.log" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latestLog) {
        return [double]::PositiveInfinity
    }
    return ((Get-Date) - $latestLog.LastWriteTime).TotalSeconds
}

$taskStatus = Get-PublisherTaskStatus
$isRunning = $taskStatus.IsRunning
$frameAge = Get-FileAgeSeconds -Path $currentFrame
$logAge = Get-LatestPublisherLogAgeSeconds
$successfulPublishAge = Get-FileAgeSeconds -Path $publishHealthFile
$withinStartupGrace = $isRunning -and $taskStatus.RunAgeSeconds -le $MaxFrameAgeSeconds

$reasons = @()
if (-not $isRunning) {
    $reasons += "task is not running"
}
if ($frameAge -gt $MaxFrameAgeSeconds) {
    $reasons += ("current frame age is {0:N1}s" -f $frameAge)
}
if ($logAge -gt $MaxLogAgeSeconds) {
    $reasons += ("publisher log age is {0:N1}s" -f $logAge)
}
if ($successfulPublishAge -gt $MaxFrameAgeSeconds -and -not $withinStartupGrace) {
    $reasons += ("successful publish age is {0:N1}s" -f $successfulPublishAge)
}

if (-not $reasons) {
    $publishHealth = if ($successfulPublishAge -le $MaxFrameAgeSeconds) {
        "successful publish age {0:N1}s" -f $successfulPublishAge
    }
    else {
        "awaiting first publish within startup grace ({0:N1}s task age)" -f $taskStatus.RunAgeSeconds
    }
    Write-WatchdogLog (
        "healthy; frame age {0:N1}s, log age {1:N1}s, {2}" -f
        $frameAge,
        $logAge,
        $publishHealth
    )
    exit 0
}

Write-WatchdogLog ("restarting publisher because " + ($reasons -join "; "))

if ($isRunning) {
    schtasks /End /TN $TaskName 2>&1 | ForEach-Object { Write-WatchdogLog $_ }
    Start-Sleep -Seconds 3
}

schtasks /Run /TN $TaskName 2>&1 | ForEach-Object { Write-WatchdogLog $_ }
