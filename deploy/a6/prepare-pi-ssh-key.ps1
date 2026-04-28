$ErrorActionPreference = "Stop"

$sshDir = Join-Path $env:USERPROFILE ".ssh"
$keyPath = Join-Path $sshDir "id_ed25519"

New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

if (-not (Test-Path $keyPath)) {
    & cmd.exe /c "ssh-keygen -t ed25519 -N """" -f ""$keyPath"""
}

Get-Content "$keyPath.pub"
