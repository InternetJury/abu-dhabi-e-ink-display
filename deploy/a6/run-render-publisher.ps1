param(
    [string]$InstallRoot = "C:\AbuDhabiEInk",
    [string]$PiHost = "ad-eink-pi",
    [string]$PiUser = "display",
    [string]$RemotePath = "/var/lib/abu-dhabi-eink/current.png",
    [string]$IdentityFile = "",
    [string]$KnownHostsFile = "",
    [int]$SleepSeconds = 60,
    [int]$MaxFrameAgeSeconds = 30,
    [int]$RenderTimeoutSeconds = 35,
    [int]$PublishCommandTimeoutSeconds = 12,
    [int]$EndToEndDeadlineSeconds = 42,
    [int]$LogRetentionDays = 14,
    [switch]$NoMinuteAlignment,
    [switch]$SkipPublish,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$appDir = Join-Path $InstallRoot "app"
$framesDir = Join-Path $InstallRoot "frames"
$logsDir = Join-Path $InstallRoot "logs"
$secretsDir = Join-Path $InstallRoot "secrets"
$cli = Join-Path $appDir ".venv\Scripts\mobility-ribbon.exe"
$currentFrame = Join-Path $framesDir "current.png"
$tempFrame = Join-Path $framesDir "current.tmp.png"
$publishHealthFile = Join-Path $logsDir "last-successful-publish.txt"
$maintenanceKeyHandoff = Join-Path $framesDir "maintenance_authorized_key.pub"

if ([string]::IsNullOrWhiteSpace($IdentityFile)) {
    $IdentityFile = Join-Path $secretsDir "publisher_ed25519"
}
if ([string]::IsNullOrWhiteSpace($KnownHostsFile)) {
    $KnownHostsFile = Join-Path $secretsDir "publisher_known_hosts"
}

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $InstallRoot "playwright"

New-Item -ItemType Directory -Force -Path $framesDir, $logsDir, $secretsDir | Out-Null

function Repair-PublisherIdentityAcl {
    if (-not (Test-Path -LiteralPath $IdentityFile)) {
        return
    }

    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($currentSid -ne "S-1-5-18") {
        return
    }

    # OpenSSH rejects a private key when an interactive account can read it.
    # Rebuild the ACL instead of using icacls /grant:r, which replaces only the
    # named principal and silently leaves unrelated user grants in place.
    $acl = Get-Acl -LiteralPath $IdentityFile
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        $acl.RemoveAccessRuleAll($rule)
    }

    $systemSid = New-Object Security.Principal.SecurityIdentifier("S-1-5-18")
    $administratorsSid = New-Object Security.Principal.SecurityIdentifier("S-1-5-32-544")
    $acl.SetOwner($systemSid)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $IdentityFile -AclObject $acl
}

Repair-PublisherIdentityAcl

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

function ConvertTo-ArgumentString {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    return ($Arguments | ForEach-Object {
        if ($_ -notmatch '[\s"]') {
            $_
        }
        else {
            '"' + ($_ -replace '"', '\"') + '"'
        }
    }) -join " "
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $argumentString = ConvertTo-ArgumentString -Arguments $Arguments
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = $FilePath
    $process.StartInfo.Arguments = $argumentString
    $process.StartInfo.UseShellExecute = $false
    # Inheriting the scheduled-task streams avoids a pipe-buffer deadlock when
    # a renderer or SSH process produces more output than WaitForExit can drain.
    $process.StartInfo.RedirectStandardOutput = $false
    $process.StartInfo.RedirectStandardError = $false
    $process.StartInfo.CreateNoWindow = $true

    try {
        if (-not $process.Start()) {
            throw "$Description failed to start."
        }

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                # Kill the whole renderer/browser or SSH process tree, not only
                # the parent that the scheduled task happens to be waiting on.
                & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            }
            catch {
                # Best effort: the caller will retry on the next aligned slot.
            }
            throw "$Description timed out after $TimeoutSeconds seconds."
        }

        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

function Install-OneTimeMaintenanceKey {
    if (-not (Test-Path -LiteralPath $maintenanceKeyHandoff)) {
        return
    }

    $maintenanceKey = (Get-Content -LiteralPath $maintenanceKeyHandoff -Raw).Trim()
    if ($maintenanceKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/]+={0,3}( [A-Za-z0-9_.@-]+)?$') {
        throw "Rejected invalid maintenance public key handoff."
    }

    $remote = "$($PiUser)@$($PiHost)"
    $sshOptions = @(
        "-i", $IdentityFile,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$KnownHostsFile",
        "-o", "ConnectTimeout=8"
    )
    $remoteCommand = @"
umask 077
mkdir -p ~/.ssh
touch ~/.ssh/authorized_keys
maintenanceKey='$maintenanceKey'
grep -qxF -- "`$maintenanceKey" ~/.ssh/authorized_keys || printf '%s\n' "`$maintenanceKey" >> ~/.ssh/authorized_keys
"@

    Invoke-ExternalCommand `
        -FilePath "ssh" `
        -Arguments ($sshOptions + @($remote, $remoteCommand)) `
        -TimeoutSeconds $PublishCommandTimeoutSeconds `
        -Description "one-time Pi maintenance key installation"

    Remove-Item -LiteralPath $maintenanceKeyHandoff -Force
    Write-Log "Installed and removed one-time Pi maintenance public-key handoff."
}

function Get-RemainingDeadlineSeconds {
    param([Parameter(Mandatory = $true)][datetime]$CycleStarted)

    $remaining = $EndToEndDeadlineSeconds - ((Get-Date) - $CycleStarted).TotalSeconds
    if ($remaining -lt 1) {
        throw "Frame missed the $EndToEndDeadlineSeconds-second end-to-end publish deadline."
    }
    return [Math]::Max(1, [int][Math]::Floor([Math]::Min($PublishCommandTimeoutSeconds, $remaining)))
}

function Publish-Frame {
    param(
        [Parameter(Mandatory = $true)][datetime]$CycleStarted,
        [Parameter(Mandatory = $true)][long]$RenderedAtUnixSeconds
    )

    if ($SkipPublish) {
        Write-Log "SkipPublish set; frame kept locally at $currentFrame"
        return
    }

    $remoteDir = Split-Path -Parent $RemotePath
    $remoteTmp = "$RemotePath.tmp"
    $remote = "$($PiUser)@$($PiHost)"
    $sshOptions = @(
        "-i", $IdentityFile,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$KnownHostsFile",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2"
    )
    $scpOptions = @(
        "-q",
        "-i", $IdentityFile,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$KnownHostsFile",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2"
    )

    Invoke-ExternalCommand `
        -FilePath "ssh" `
        -Arguments ($sshOptions + @($remote, "mkdir -p '$remoteDir'")) `
        -TimeoutSeconds (Get-RemainingDeadlineSeconds -CycleStarted $CycleStarted) `
        -Description "remote frame directory check on $remote"

    Invoke-ExternalCommand `
        -FilePath "scp" `
        -Arguments ($scpOptions + @($currentFrame, "$($remote):$remoteTmp")) `
        -TimeoutSeconds (Get-RemainingDeadlineSeconds -CycleStarted $CycleStarted) `
        -Description "frame copy to $remote"

    Invoke-ExternalCommand `
        -FilePath "ssh" `
        -Arguments ($sshOptions + @($remote, "touch -m -d '@$RenderedAtUnixSeconds' '$remoteTmp' && mv -f '$remoteTmp' '$RemotePath'")) `
        -TimeoutSeconds (Get-RemainingDeadlineSeconds -CycleStarted $CycleStarted) `
        -Description "atomic frame publish on $remote"
}

if (-not (Test-Path $cli)) {
    throw "mobility-ribbon executable not found at $cli. Run deploy\a6\install-a6.ps1 first."
}
if (-not $SkipPublish -and -not (Test-Path -LiteralPath $IdentityFile)) {
    throw "Publisher SSH key not found at $IdentityFile. Run deploy\a6\install-a6.ps1 first."
}

Install-OneTimeMaintenanceKey

do {
    try {
        Invoke-StorageCleanup
        Wait-UntilNextRenderSlot

        $renderStarted = Get-Date
        Invoke-ExternalCommand `
            -FilePath $cli `
            -Arguments @("render-live", "--output", $tempFrame, "--use-playwright-fallback") `
            -TimeoutSeconds $RenderTimeoutSeconds `
            -Description "render-live"

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
        $renderedAtUnixSeconds = [DateTimeOffset]::new($renderStarted).ToUnixTimeSeconds()
        Publish-Frame -CycleStarted $renderStarted -RenderedAtUnixSeconds $renderedAtUnixSeconds
        Set-Content -LiteralPath $publishHealthFile -Value ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
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
