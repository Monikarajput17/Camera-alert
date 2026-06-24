# Makes Camera Alert launch automatically (hidden) at logon, no admin required.
# It drops a shortcut in your Startup folder that runs the dashboard with
# pythonw.exe (which has no console window).
#
# Usage:  powershell -ExecutionPolicy Bypass -File deploy\install-autostart.ps1
# Remove: powershell -ExecutionPolicy Bypass -File deploy\uninstall-autostart.ps1

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot            # project root
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe" # pythonw = no console window

if (-not (Test-Path $pythonw)) {
    throw "Virtual environment not found at $pythonw. Create it first: python -m venv .venv"
}

$startup = [Environment]::GetFolderPath('Startup')
$linkPath = Join-Path $startup 'CameraAlert.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($linkPath)
$sc.TargetPath       = $pythonw
$sc.Arguments        = '-m webapp'
$sc.WorkingDirectory = $root
$sc.WindowStyle      = 7   # minimized / hidden
$sc.Description       = 'Camera Alert dashboard (http://localhost:8000)'
$sc.Save()

Write-Host "[OK] Installed auto-start shortcut:"
Write-Host "     $linkPath"
Write-Host "     Camera Alert will launch at every logon -> http://localhost:8000"
Write-Host ""
Write-Host "     Start it right now without rebooting:"
Write-Host "       Start-Process '$pythonw' -ArgumentList '-m','webapp' -WorkingDirectory '$root'"
