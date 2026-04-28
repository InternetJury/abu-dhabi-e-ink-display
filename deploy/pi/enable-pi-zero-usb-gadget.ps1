param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z]$")]
    [string]$BootDriveLetter,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$drive = ($BootDriveLetter.TrimEnd(":")).ToUpperInvariant()
$root = "$($drive):\"
$configPath = Join-Path $root "config.txt"
$cmdlinePath = Join-Path $root "cmdline.txt"

function Assert-BootPartition {
    if (-not (Test-Path $root)) {
        throw "Drive $root does not exist."
    }

    $volume = Get-Volume -DriveLetter $drive -ErrorAction Stop
    if ($volume.DriveType -ne "Removable" -and -not $Force) {
        throw "Drive $root is not reported as removable. Re-run with -Force only if you are certain this is the Pi boot partition."
    }

    if (-not (Test-Path $configPath) -or -not (Test-Path $cmdlinePath)) {
        throw "Drive $root does not look like a Raspberry Pi boot partition because config.txt or cmdline.txt is missing."
    }
}

function Add-ConfigLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Line
    )

    $content = Get-Content -LiteralPath $Path -Raw
    if ($content -notmatch "(?m)^\s*$([regex]::Escape($Line))\s*$") {
        Add-Content -LiteralPath $Path -Value "`r`n$Line"
    }
}

function Add-CmdlineModule {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ModuleValue
    )

    $content = (Get-Content -LiteralPath $Path -Raw).Trim()
    if ($content -match "(^|\s)modules-load=([^\s]+)") {
        $existing = $Matches[2].Split(",") | Where-Object { $_ }
        $wanted = $ModuleValue.Split(",") | Where-Object { $_ }
        $merged = @($existing + $wanted | Select-Object -Unique) -join ","
        $content = [regex]::Replace($content, "(^|\s)modules-load=([^\s]+)", " modules-load=$merged").Trim()
    }
    else {
        $content = "$content modules-load=$ModuleValue".Trim()
    }
    Set-Content -LiteralPath $Path -Value $content -NoNewline
}

Assert-BootPartition

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item -LiteralPath $configPath -Destination "$configPath.$stamp.bak"
Copy-Item -LiteralPath $cmdlinePath -Destination "$cmdlinePath.$stamp.bak"

Add-ConfigLine -Path $configPath -Line "dtoverlay=dwc2"
Add-CmdlineModule -Path $cmdlinePath -ModuleValue "dwc2,g_ether"

Write-Host "Pi Zero USB gadget networking enabled on $root."
Write-Host "Backups:"
Write-Host "  $configPath.$stamp.bak"
Write-Host "  $cmdlinePath.$stamp.bak"
Write-Host "Insert the card into the Pi Zero 2 W and connect the data USB port to this PC."
