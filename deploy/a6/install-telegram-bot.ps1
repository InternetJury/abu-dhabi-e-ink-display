param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$PiHost = "ad-eink-pi.local",
    [string]$PiUser = "display",
    [switch]$RegisterTask
)

$ErrorActionPreference = "Stop"

$appDir = Join-Path $InstallRoot "app"
$secretsDir = Join-Path $InstallRoot "secrets"
$stateDir = Join-Path $InstallRoot "state"
$logsDir = Join-Path $InstallRoot "logs"
$configPath = Join-Path $secretsDir "telegram-bot.env"

New-Item -ItemType Directory -Force -Path $secretsDir, $stateDir, $logsDir | Out-Null
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $secretsDir /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "$($currentIdentity):(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restrict permissions on $secretsDir."
}

if (-not (Test-Path $appDir)) {
    throw "App checkout not found at $appDir. Run deploy\a6\install-a6.ps1 first."
}

if (-not (Test-Path $configPath)) {
    @"
# Local-only Telegram bot config.
# Do not commit this file or paste it into public issue trackers.
TELEGRAM_BOT_TOKEN=PASTE_BOTFATHER_TOKEN_HERE
TELEGRAM_ALLOWED_USER_IDS=
PI_HOST=$PiHost
PI_USER=$PiUser
SSH_PATH=ssh
SSH_IDENTITY_FILE=$InstallRoot\secrets\publisher_ed25519
SSH_KNOWN_HOSTS_FILE=$InstallRoot\secrets\publisher_known_hosts
TELEGRAM_CONFIRM_TTL_SECONDS=60
TELEGRAM_SHUTDOWN_COOLDOWN_SECONDS=300
TELEGRAM_POLL_TIMEOUT_SECONDS=30
TELEGRAM_DRY_RUN=false
"@ | Set-Content -Path $configPath -Encoding UTF8
    Write-Host "Created local config template: $configPath"
}
else {
    Write-Host "Keeping existing local config: $configPath"
    $existingConfig = Get-Content -LiteralPath $configPath
    if (-not ($existingConfig -match '^SSH_IDENTITY_FILE=')) {
        Add-Content -LiteralPath $configPath -Value "SSH_IDENTITY_FILE=$InstallRoot\secrets\publisher_ed25519"
    }
    if (-not ($existingConfig -match '^SSH_KNOWN_HOSTS_FILE=')) {
        Add-Content -LiteralPath $configPath -Value "SSH_KNOWN_HOSTS_FILE=$InstallRoot\secrets\publisher_known_hosts"
    }
}

if ($RegisterTask) {
    $runner = Join-Path $appDir "deploy\a6\run-telegram-bot.ps1"
    if (-not (Test-Path $runner)) {
        throw "Bot runner not found at $runner."
    }

    $taskName = "Abu Dhabi E-Ink Telegram Control Bot"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$runner`"",
        "-InstallRoot", "`"$InstallRoot`""
    ) -join " "

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -MultipleInstances IgnoreNew

    Write-Host "Registering scheduled task: $taskName"
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
}

Write-Host "Telegram bot setup prepared."
Write-Host "Config: $configPath"
Write-Host "Next:"
Write-Host "  1. Create a bot with @BotFather and paste the token into TELEGRAM_BOT_TOKEN."
Write-Host "  2. Run the bot once, send /whoami from each approved Telegram account, then fill TELEGRAM_ALLOWED_USER_IDS."
Write-Host "  3. Start or re-run the scheduled task after the config is complete."
