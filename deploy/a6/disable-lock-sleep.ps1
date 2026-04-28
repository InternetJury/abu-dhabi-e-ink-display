$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Host "Disabling sleep, hibernate, display timeout, and secure screensaver for this Windows profile..."

powercfg /hibernate off
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0

$desktopKey = "HKCU:\Control Panel\Desktop"
Set-ItemProperty -Path $desktopKey -Name ScreenSaveActive -Value "0"
Set-ItemProperty -Path $desktopKey -Name ScreenSaverIsSecure -Value "0"
Set-ItemProperty -Path $desktopKey -Name ScreenSaveTimeOut -Value "0"

if (Test-IsAdmin) {
    $systemPolicyKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    New-Item -Path $systemPolicyKey -Force | Out-Null
    New-ItemProperty -Path $systemPolicyKey -Name InactivityTimeoutSecs -PropertyType DWord -Value 0 -Force | Out-Null

    $lockScreenKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization"
    New-Item -Path $lockScreenKey -Force | Out-Null
    New-ItemProperty -Path $lockScreenKey -Name NoLockScreen -PropertyType DWord -Value 1 -Force | Out-Null
}
else {
    Write-Warning "Not running as Administrator; machine-level lock-screen policies were not changed."
}

Write-Host "Power and lock timeout policy updated."
