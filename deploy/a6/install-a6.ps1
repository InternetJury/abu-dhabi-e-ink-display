param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$RepoUrl = "https://github.com/InternetJury/abu-dhabi-e-ink-display.git",
    [string]$PiHost = "ad-eink-pi",
    [string]$PiUser = "display",
    [switch]$RegisterTask,
    [switch]$DisableLockSleep
)

$ErrorActionPreference = "Stop"

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-Command winget)) {
        throw "winget is required to install $Name. Install App Installer from Microsoft Store, then rerun this script."
    }

    Write-Host "Installing or updating $Name..."
    winget install --id $Id --exact --silent --accept-source-agreements --accept-package-agreements
}

function Get-Python311 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & py -3.11 --version | Out-Null
            return "py -3.11"
        }
        catch {
            # Fall through to python command check.
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq "3.11") {
            return "python"
        }
    }

    Install-WingetPackage -Id "Python.Python.3.11" -Name "Python 3.11"
    return "py -3.11"
}

if (-not (Test-Command git)) {
    Install-WingetPackage -Id "Git.Git" -Name "Git"
}

$pythonCommand = Get-Python311

$root = New-Item -ItemType Directory -Force -Path $InstallRoot
$appDir = Join-Path $root.FullName "app"
$framesDir = Join-Path $root.FullName "frames"
$logsDir = Join-Path $root.FullName "logs"
New-Item -ItemType Directory -Force -Path $framesDir, $logsDir | Out-Null

if (-not (Test-Path $appDir)) {
    Write-Host "Cloning project into $appDir..."
    git clone $RepoUrl $appDir
}
else {
    Write-Host "Updating existing checkout in $appDir..."
    git -C $appDir pull --ff-only
}

$venvDir = Join-Path $appDir ".venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating Python virtual environment..."
    Invoke-Expression "$pythonCommand -m venv `"$venvDir`""
}

$pythonExe = Join-Path $venvDir "Scripts\python.exe"
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -e $appDir
& $pythonExe -m playwright install chromium

if ($DisableLockSleep) {
    $disableScript = Join-Path $appDir "deploy\a6\disable-lock-sleep.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $disableScript
}

if ($RegisterTask) {
    $runner = Join-Path $appDir "deploy\a6\run-render-publisher.ps1"
    $taskName = "Abu Dhabi E-Ink Render Publisher"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$runner`"",
        "-InstallRoot", "`"$InstallRoot`"",
        "-PiHost", "`"$PiHost`"",
        "-PiUser", "`"$PiUser`""
    ) -join " "

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    Write-Host "Registering scheduled task: $taskName"
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
}

Write-Host "A6 setup complete."
Write-Host "App:    $appDir"
Write-Host "Frames: $framesDir"
Write-Host "Logs:   $logsDir"
Write-Host "Run loop manually with:"
Write-Host "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$appDir\deploy\a6\run-render-publisher.ps1`" -InstallRoot `"$InstallRoot`" -PiHost `"$PiHost`" -PiUser `"$PiUser`""
