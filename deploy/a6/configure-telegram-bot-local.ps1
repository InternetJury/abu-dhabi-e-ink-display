param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [switch]$EnableTask,
    [switch]$StartTask
)

$ErrorActionPreference = "Stop"

$configPath = Join-Path $InstallRoot "secrets\telegram-bot.env"
$taskName = "Abu Dhabi E-Ink Telegram Control Bot"

if (-not (Test-Path $configPath)) {
    throw "Telegram bot config not found at $configPath. Run install-telegram-bot.ps1 first."
}

$token = Read-Host "Paste the regenerated BotFather token"
if (-not $token -or $token -eq "PASTE_BOTFATHER_TOKEN_HERE") {
    throw "A real regenerated BotFather token is required."
}

$allowedIds = Read-Host "Paste allowed numeric Telegram user IDs separated by commas, or press Enter to keep/discover later"
$existingAllowedIds = ($lines | Where-Object { $_ -like "TELEGRAM_ALLOWED_USER_IDS=*" } | Select-Object -First 1) -replace "^TELEGRAM_ALLOWED_USER_IDS=", ""
if (($EnableTask -or $StartTask) -and -not $allowedIds -and -not $existingAllowedIds) {
    throw "Allowed Telegram user IDs are required before enabling or starting the scheduled task."
}

$lines = Get-Content -Path $configPath
$updated = foreach ($line in $lines) {
    if ($line -like "TELEGRAM_BOT_TOKEN=*") {
        "TELEGRAM_BOT_TOKEN=$token"
    }
    elseif ($line -like "TELEGRAM_ALLOWED_USER_IDS=*") {
        if ($allowedIds) {
            "TELEGRAM_ALLOWED_USER_IDS=$allowedIds"
        }
        else {
            $line
        }
    }
    else {
        $line
    }
}

$updated | Set-Content -Path $configPath -Encoding UTF8
Write-Host "Updated local Telegram bot config at $configPath"

if ($EnableTask) {
    Enable-ScheduledTask -TaskName $taskName | Out-Null
    Write-Host "Enabled scheduled task: $taskName"
}

if ($StartTask) {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Started scheduled task: $taskName"
}
