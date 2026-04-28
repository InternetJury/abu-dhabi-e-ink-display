param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$PiHost = "ad-eink-pi",
    [string]$PiUser = "display",
    [string]$RemotePath = "/var/lib/abu-dhabi-eink/current.png",
    [int]$SleepSeconds = 60,
    [int]$MaxFrameAgeSeconds = 45,
    [int]$LogRetentionDays = 14,
    [switch]$NoMinuteAlignment,
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

function Invoke-StorageCleanup {
    $cutoff = (Get-Date).AddDays(-1 * $LogRetentionDays)
    Get-ChildItem -Path $logsDir -Filter "render-publisher-*.log" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    # The publisher is intentionally current-frame only. Remove interrupted temp files.
    Get-ChildItem -Path $framesDir -Filter "*.tmp.png" -File -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Wait-UntilNextRenderSlot {
    if ($NoMinuteAlignment -or $Once) {
        return
    }

    $now = Get-Date
    $secondsSinceMidnight = [int][Math]::Floor($now.TimeOfDay.TotalSeconds)
    $remainder = $secondsSinceMidnight % $SleepSeconds
    $delaySeconds = $SleepSeconds - $remainder - ($now.Millisecond / 1000.0)
    if ($delaySeconds -ge $SleepSeconds - 0.25) {
        $delaySeconds = 0
    }

    if ($delaySeconds -gt 0) {
        Write-Log ("Waiting {0:N1}s for the next aligned render slot." -f $delaySeconds)
        Start-Sleep -Milliseconds ([int][Math]::Ceiling($delaySeconds * 1000))
    }
}

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
        Invoke-StorageCleanup
        Wait-UntilNextRenderSlot

        $renderStarted = Get-Date
        & $cli render-live --output $tempFrame --use-playwright-fallback
        if ($LASTEXITCODE -ne 0) {
            throw "render-live failed with exit code $LASTEXITCODE."
        }

        $renderAgeSeconds = ((Get-Date) - $renderStarted).TotalSeconds
        if ($renderAgeSeconds -gt $MaxFrameAgeSeconds) {
            Remove-Item -LiteralPath $tempFrame -Force -ErrorAction SilentlyContinue
            Write-Log (
                "Skipped publishing stale frame; render took {0:N1}s, max allowed is {1}s." -f
                $renderAgeSeconds,
                $MaxFrameAgeSeconds
            )
            if ($Once) {
                break
            }
            continue
        }

        Move-Item -Path $tempFrame -Destination $currentFrame -Force
        Publish-Frame
        Write-Log (
            "Rendered and published $currentFrame to $($PiUser)@$($PiHost):$RemotePath in {0:N1}s" -f
            $renderAgeSeconds
        )
    }
    catch {
        Write-Log "ERROR: $($_.Exception.Message)"
    }

    if ($Once) {
        break
    }

    if ($NoMinuteAlignment) {
        Start-Sleep -Seconds $SleepSeconds
    }
} while ($true)
