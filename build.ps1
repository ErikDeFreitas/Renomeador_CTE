# Gera os dois executaveis (RenomeadorCTE.exe e RenomeadorXML.exe) e os arquivos .sha256 de cada Release.
# Antes: aumente __version__ em src\renomeador_cte\__init__.py (a versao e a mesma para os dois).
# Uso:  powershell -File build.ps1 [-Python <caminho do python>]
param([string]$Python)
Set-Location $PSScriptRoot
if (-not $Python) {
    $venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}

function Gerar([string]$nome, [string]$script) {
    $exe = "dist\$nome.exe"
    $antes = if (Test-Path $exe) { (Get-Item $exe).LastWriteTime } else { [datetime]::MinValue }
    & $Python -m PyInstaller --noconfirm --onefile --windowed --name $nome `
        --icon "$PSScriptRoot/assets/app.ico" `
        --collect-data tcm_ui --collect-data renomeador_cte `
        --exclude-module tkinter --exclude-module numpy --exclude-module PIL --exclude-module matplotlib `
        --exclude-module pandas --exclude-module pytest --exclude-module PySide6.QtWebEngineCore `
        --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick `
        --exclude-module PySide6.QtPdf --exclude-module PySide6.QtMultimedia `
        --workpath "build\$nome" --specpath build --distpath dist $script
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exe) -or (Get-Item $exe).LastWriteTime -le $antes) {
        Write-Host "`nERRO: o build de $nome falhou; nenhum arquivo novo foi gerado." -ForegroundColor Red
        exit 1
    }
    $hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
    [IO.File]::WriteAllText("$PSScriptRoot\dist\$nome.exe.sha256", "$hash  $nome.exe`n")
    Write-Host "$nome.exe | SHA-256 $hash"
}

Gerar "RenomeadorCTE" "main.py"
Gerar "RenomeadorXML" "main_xml.py"

$versao = (Select-String -Path src\renomeador_cte\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "`nPronto: versao $versao"
Write-Host "Publique em uma Release com a tag v$versao anexando os QUATRO arquivos de dist\:"
Write-Host "  RenomeadorCTE.exe, RenomeadorCTE.exe.sha256, RenomeadorXML.exe e RenomeadorXML.exe.sha256"
