param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$PiHost = "ad-eink-pi",
    [string]$PiUser = "display",
    [string]$RemotePath = "/var/lib/abu-dhabi-eink/current.png",
    [int]$SleepSeconds = 60,
    [switch]$SkipPublish,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$appDir = Join-Path $InstallRoot "app"
$framesDir = Join-Path $InstallRoot "frames"
$logsDir = Join-Path $InstallRoot "logs"
$cli = Join-Path $appDir ".venv\Scripts\mobility-ribbon.exe"
$currentFrame = Join-Path $framesDir "current.png"
$tempFrame = Join-Path $framesDir "current.tmp.png"

New-Item -ItemType Directory -Force -Path $framesDir, $logsDir | Out-Null

function Write-Log {
    param([Parameter(Mandatory = $true)][string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    $logPath = Join-Path $logsDir ("render-publisher-" + (Get-Date -Format "yyyyMMdd") + ".log")
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

function Publish-Frame {
    if ($SkipPublish) {
        Write-Log "SkipPublish set; frame kept locally at $currentFrame"
        return
    }

    $remoteDir = Split-Path -Parent $RemotePath
    $remoteTmp = "$RemotePath.tmp"
    $remote = "$($PiUser)@$($PiHost)"

    & ssh $remote "mkdir -p '$remoteDir'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create remote frame directory on $remote."
    }

    & scp -q $currentFrame "$($remote):$remoteTmp"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy frame to $remote."
    }

    & ssh $remote "mv '$remoteTmp' '$RemotePath'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to publish frame atomically on $remote."
    }
}

if (-not (Test-Path $cli)) {
    throw "mobility-ribbon executable not found at $cli. Run deploy\a6\install-a6.ps1 first."
}

do {
    try {
        & $cli render-live --output $tempFrame --use-playwright-fallback
        if ($LASTEXITCODE -ne 0) {
            throw "render-live failed with exit code $LASTEXITCODE."
        }

        Move-Item -Path $tempFrame -Destination $currentFrame -Force
        Publish-Frame
        Write-Log "Rendered and published $currentFrame to $($PiUser)@$($PiHost):$RemotePath"
    }
    catch {
        Write-Log "ERROR: $($_.Exception.Message)"
    }

    if ($Once) {
        break
    }

    Start-Sleep -Seconds $SleepSeconds
} while ($true)
