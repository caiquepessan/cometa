# Desinstala o Cometa (chamado por Configurações > Aplicativos).
# Os seus cronômetros (%APPDATA%\Cometa) são mantidos.
$ErrorActionPreference = 'SilentlyContinue'
$dest = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = 'Cometa'

Get-Process Cometa | ForEach-Object { taskkill /PID $_.Id | Out-Null }
Start-Sleep -Seconds 2
Get-Process Cometa | Stop-Process -Force

foreach ($folder in [Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop')) {
    Remove-Item -Force (Join-Path $folder "$name.lnk")
}
Remove-Item -Recurse -Force 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Cometa'

# The folder holds this very script, so it is removed right after the script ends.
Start-Process cmd.exe -WindowStyle Hidden -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$dest`""
