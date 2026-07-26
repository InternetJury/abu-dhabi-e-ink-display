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
    & winget install --id $Id --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "$Name installation failed with exit code $LASTEXITCODE."
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Get-CompatiblePython {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $runtimes = & py -0p 2>$null
        foreach ($line in $runtimes) {
            if ($line -match "-V:(\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                    return [pscustomobject]@{
                        Exe = "py"
                        Args = @("-$major.$minor")
                    }
                }
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        $parts = $version.Split(".")
        if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) {
            return [pscustomobject]@{
                Exe = "python"
                Args = @()
            }
        }
    }

    Install-WingetPackage -Id "Python.Python.3.11" -Name "Python 3.11"
    return [pscustomobject]@{
        Exe = "py"
        Args = @("-3.11")
    }
}

function Invoke-CompatiblePython {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $pythonArgs = @()
    $pythonArgs += @($script:PythonCommand.Args)
    $pythonArgs += $Arguments

    & $script:PythonCommand.Exe @pythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($script:PythonCommand.Exe) $($pythonArgs -join ' ')"
    }
}

if (-not (Test-Command git)) {
    Install-WingetPackage -Id "Git.Git" -Name "Git"
}

$script:PythonCommand = Get-CompatiblePython

$root = New-Item -ItemType Directory -Force -Path $InstallRoot
$appDir = Join-Path $root.FullName "app"
$framesDir = Join-Path $root.FullName "frames"
$logsDir = Join-Path $root.FullName "logs"
$secretsDir = Join-Path $root.FullName "secrets"
$playwrightDir = Join-Path $root.FullName "playwright"
New-Item -ItemType Directory -Force -Path $framesDir, $logsDir, $secretsDir, $playwrightDir | Out-Null

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $secretsDir /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "$($currentIdentity):(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restrict permissions on $secretsDir."
}

$publisherKey = Join-Path $secretsDir "publisher_ed25519"
$knownHostsFile = Join-Path $secretsDir "publisher_known_hosts"
$sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
if (-not (Test-Path -LiteralPath $sshKeygen)) {
    throw "Windows OpenSSH Client is required at $sshKeygen. Install the OpenSSH Client capability, then rerun this script."
}
if (-not (Test-Path -LiteralPath $publisherKey)) {
    Write-Host "Generating dedicated A6-to-Pi publisher key..."
    Invoke-CheckedCommand `
        -FilePath $sshKeygen `
        -Arguments @("-q", "-t", "ed25519", "-N", '""', "-C", "abu-dhabi-eink-publisher", "-f", $publisherKey) `
        -Description "Publisher SSH key generation"
}

if (-not (Test-Path $appDir)) {
    Write-Host "Cloning project into $appDir..."
    Invoke-CheckedCommand -FilePath "git" -Arguments @("clone", $RepoUrl, $appDir) -Description "Project clone"
}
else {
    Write-Host "Updating existing checkout in $appDir..."
    Invoke-CheckedCommand -FilePath "git" -Arguments @("-C", $appDir, "pull", "--ff-only") -Description "Project update"
}

$venvDir = Join-Path $appDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
if ((Test-Path $venvDir) -and -not (Test-Path $pythonExe)) {
    Write-Warning "Existing virtual environment is incomplete; recreating $venvDir."
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating Python virtual environment..."
    Invoke-CompatiblePython -Arguments @("-m", "venv", $venvDir)
}

if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment creation failed; expected Python at $pythonExe."
}

Invoke-CheckedCommand -FilePath $pythonExe -Arguments @("-m", "pip", "install", "--upgrade", "pip") -Description "pip upgrade"
Invoke-CheckedCommand -FilePath $pythonExe -Arguments @("-m", "pip", "install", "-e", $appDir) -Description "Project dependency install"
$env:PLAYWRIGHT_BROWSERS_PATH = $playwrightDir
Invoke-CheckedCommand -FilePath $pythonExe -Arguments @("-m", "playwright", "install", "chromium") -Description "Playwright Chromium install"

if ($DisableLockSleep) {
    $disableScript = Join-Path $appDir "deploy\a6\disable-lock-sleep.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $disableScript
    if ($LASTEXITCODE -ne 0) {
        throw "Lock/sleep policy update failed with exit code $LASTEXITCODE."
    }
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
        "-PiUser", "`"$PiUser`"",
        "-IdentityFile", "`"$publisherKey`"",
        "-KnownHostsFile", "`"$knownHostsFile`""
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

    $watchdog = Join-Path $appDir "deploy\a6\watch-render-publisher.ps1"
    $watchdogTaskName = "Abu Dhabi E-Ink Publisher Watchdog"
    $watchdogCommand = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -InstallRoot "{1}"' -f
        $watchdog,
        $InstallRoot
    )

    Write-Host "Registering scheduled task: $watchdogTaskName"
    & schtasks /Create /TN $watchdogTaskName /SC MINUTE /MO 1 /TR $watchdogCommand /RU SYSTEM /RL HIGHEST /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Publisher watchdog task registration failed with exit code $LASTEXITCODE."
    }
}

Write-Host "A6 setup complete."
Write-Host "App:    $appDir"
Write-Host "Frames: $framesDir"
Write-Host "Logs:   $logsDir"
Write-Host "Publisher public key (authorize this once on the Pi):"
Get-Content -LiteralPath "$publisherKey.pub"
Write-Host "Run loop manually with:"
Write-Host "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$appDir\deploy\a6\run-render-publisher.ps1`" -InstallRoot `"$InstallRoot`" -PiHost `"$PiHost`" -PiUser `"$PiUser`""
