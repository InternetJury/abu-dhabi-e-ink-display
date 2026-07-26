$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    if ([string]::IsNullOrWhiteSpace($PSCommandPath)) {
        throw "Unable to determine the script path for Administrator elevation."
    }

    Write-Host "Requesting Administrator access to enable OpenSSH Server..."
    $elevatedArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $elevated = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $elevatedArguments `
        -Verb RunAs `
        -Wait `
        -PassThru
    exit $elevated.ExitCode
}

Write-Host "Installing or enabling Windows OpenSSH Server..."
$capability = Get-WindowsCapability -Online | Where-Object { $_.Name -like "OpenSSH.Server*" } | Select-Object -First 1
if (-not $capability) {
    throw "OpenSSH Server capability was not found on this Windows installation."
}

if ($capability.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $capability.Name | Out-Null
}

Write-Host "Starting sshd and setting it to automatic startup..."
Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd

$agent = Get-Service -Name ssh-agent -ErrorAction SilentlyContinue
if ($agent) {
    Set-Service -Name ssh-agent -StartupType Manual
}

Write-Host "Opening the Windows firewall rule for OpenSSH..."
$rule = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if ($rule) {
    Set-NetFirewallRule `
        -Name "OpenSSH-Server-In-TCP" `
        -Enabled True `
        -Profile Any `
        -RemoteAddress @("100.64.0.0/10", "LocalSubnet")
}
else {
    New-NetFirewallRule `
        -Name "OpenSSH-Server-In-TCP" `
        -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort 22 `
        -Profile Any `
        -RemoteAddress @("100.64.0.0/10", "LocalSubnet") | Out-Null
}

Write-Host "OpenSSH Server is ready."
Write-Host "Validate from this PC with:"
Write-Host "  ssh <A6_TAILSCALE_IP_OR_HOSTNAME> hostname"
