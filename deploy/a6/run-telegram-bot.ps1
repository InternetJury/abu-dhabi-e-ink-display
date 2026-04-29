param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$ConfigPath = "",
    [string]$StateFile = "",
    [string]$LogFile = "",
    [switch]$DryRun,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$appDir = Join-Path $InstallRoot "app"
$pythonExe = Join-Path $appDir ".venv\Scripts\python.exe"
$botScript = Join-Path $appDir "deploy\a6\telegram-shutdown-bot.py"
$logsDir = Join-Path $InstallRoot "logs"
$stateDir = Join-Path $InstallRoot "state"
$secretsDir = Join-Path $InstallRoot "secrets"

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $secretsDir "telegram-bot.env"
}
if (-not $StateFile) {
    $StateFile = Join-Path $stateDir "telegram-bot-state.json"
}
if (-not $LogFile) {
    $LogFile = Join-Path $logsDir "telegram-bot.log"
}

New-Item -ItemType Directory -Force -Path $logsDir, $stateDir, $secretsDir | Out-Null

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe. Run deploy\a6\install-a6.ps1 first."
}
if (-not (Test-Path $botScript)) {
    throw "Telegram bot script not found at $botScript."
}
if (-not (Test-Path $ConfigPath)) {
    throw "Telegram bot config not found at $ConfigPath. Run deploy\a6\install-telegram-bot.ps1 and fill in the local token."
}

$arguments = @(
    $botScript,
    "--config", $ConfigPath,
    "--state-file", $StateFile,
    "--log-file", $LogFile
)

if ($DryRun) {
    $arguments += "--dry-run"
}
if ($Once) {
    $arguments += "--once"
}

& $pythonExe @arguments
exit $LASTEXITCODE
