# Instala o Cometa para o usuário atual (não precisa de administrador).
# Executado por "Instalar Cometa.cmd", ao lado deste arquivo.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = 'Cometa'
$dest = Join-Path $env:LOCALAPPDATA 'Programs\Cometa'
$exe = Join-Path $dest 'app\Cometa.exe'

function Step($text) { Write-Host "  - $text" }

try {
    Write-Host ""
    Write-Host "  Instalando o $name..." -ForegroundColor Cyan
    Write-Host ""

    # 1. Fecha o app se estiver aberto. Ele salva ao fechar e guarda o tempo como
    #    horário de início, então nenhum cronômetro perde tempo.
    $running = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in 'Cometa.exe', 'Cronometro.exe' -or
        (($_.Name -in 'python.exe', 'pythonw.exe') -and
         ($_.CommandLine -like '*Cometa.pyw*' -or $_.CommandLine -like '*Cronometro.pyw*'))
    }
    if ($running) {
        Step 'Fechando o app aberto'
        foreach ($p in $running) { taskkill /PID $p.ProcessId | Out-Null }
        $deadline = (Get-Date).AddSeconds(6)
        while ((Get-Date) -lt $deadline -and ($running | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })) {
            Start-Sleep -Milliseconds 200
        }
    }

    # 2. As versões de teste anteriores se chamavam "Cronômetro": remove aquela
    #    instalação. Os cronômetros dela são aproveitados pelo Cometa.
    $legacy = Join-Path $env:LOCALAPPDATA 'Programs\Cronometro\uninstall.ps1'
    if (Test-Path $legacy) {
        Step 'Removendo a versão anterior (Cronômetro)'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $legacy
    }

    # 3. Copia o aplicativo.
    Step "Copiando para $dest"
    New-Item -ItemType Directory -Force $dest | Out-Null
    $target = Join-Path $dest 'app'
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse (Join-Path $here 'app') $target
    Copy-Item -Force (Join-Path $here 'uninstall.ps1') (Join-Path $dest 'uninstall.ps1')

    # 4. Atalhos no Menu Iniciar e na Área de Trabalho.
    Step 'Criando atalhos (Menu Iniciar e Área de Trabalho)'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in [Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop')) {
        $link = $shell.CreateShortcut((Join-Path $folder "$name.lnk"))
        $link.TargetPath = $exe
        $link.WorkingDirectory = Split-Path $exe
        $link.IconLocation = "$exe,0"
        $link.Description = 'Cronômetros de vidro que flutuam na área de trabalho'
        $link.Save()
    }

    # 5. Registra em Configurações > Aplicativos, para poder desinstalar por lá.
    Step 'Registrando em Configurações > Aplicativos'
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Cometa'
    New-Item -Path $key -Force | Out-Null
    $version = (Get-Item $exe).VersionInfo.ProductVersion
    $size = [int]((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
    $values = @{
        DisplayName     = $name
        DisplayVersion  = $version
        Publisher       = $name
        DisplayIcon     = "$exe,0"
        InstallLocation = $dest
        UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$dest\uninstall.ps1`""
    }
    foreach ($entry in $values.GetEnumerator()) { Set-ItemProperty -Path $key -Name $entry.Key -Value $entry.Value }
    Set-ItemProperty -Path $key -Name EstimatedSize -Value $size -Type DWord
    Set-ItemProperty -Path $key -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $key -Name NoRepair -Value 1 -Type DWord

    # 6. Abre o app instalado.
    Step "Abrindo o $name"
    Start-Process $exe
    "$(Get-Date -Format s) $name $version instalado em $dest" | Set-Content -Encoding UTF8 (Join-Path $dest 'install.log')

    Write-Host ""
    Write-Host "  Pronto! O $name está instalado." -ForegroundColor Green
    Write-Host "  Esta pasta do instalador já pode ser apagada."
    Start-Sleep -Seconds 4
}
catch {
    Write-Host ""
    Write-Host "  A instalação falhou: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host '  Pressione Enter para fechar'
    exit 1
}
