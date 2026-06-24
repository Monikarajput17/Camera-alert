# Removes the Camera Alert auto-start shortcut from the Startup folder.
# Usage:  powershell -ExecutionPolicy Bypass -File deploy\uninstall-autostart.ps1

$ErrorActionPreference = "Stop"
$startup  = [Environment]::GetFolderPath('Startup')
$linkPath = Join-Path $startup 'CameraAlert.lnk'

if (Test-Path $linkPath) {
    Remove-Item $linkPath -Force
    Write-Host "[OK] Removed auto-start shortcut. Camera Alert will no longer launch at logon."
} else {
    Write-Host "[..] No auto-start shortcut found. Nothing to do."
}
