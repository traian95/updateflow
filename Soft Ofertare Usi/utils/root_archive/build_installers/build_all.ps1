# Build exe Ofertare + Admin si pregatire output pentru instalatoare.
# Ruleaza din: build_installers\  sau din radacina proiectului.
# Cerinte: Python cu pyinstaller, logo.ico + Naturen2.png (si despre.gif pentru Ofertare) in radacina proiectului.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path

Write-Host "Radacina proiect: $Root" -ForegroundColor Cyan
Set-Location $Root

# Cautare asset-uri: intai in radacina proiectului, apoi in build_installers\assets
$AssetsRoot = $Root
$AssetsDir = Join-Path $ScriptDir "assets"
$required = @{
    "logo.ico" = "Icon aplicatie (folosit de ambele exe)"
    "Naturen2.png" = "Logo afisat in aplicatie"
}
$optional = @{
    "despre.gif" = "GIF pentru ecranul Despre (doar Ofertare; lipsa = mesaj eroare la Despre)"
}
foreach ($f in $required.Keys) {
    $p = Join-Path $Root $f
    if (-not (Test-Path $p)) { $p = Join-Path $AssetsDir $f }
    if (-not (Test-Path $p)) {
        Write-Host "LIPSESTE: $f - $($required[$f])" -ForegroundColor Red
        Write-Host "Adauga $f in: $Root  sau  $AssetsDir" -ForegroundColor Yellow
        exit 1
    }
}
foreach ($f in $optional.Keys) {
    $p = Join-Path $Root $f
    if (-not (Test-Path $p)) { $p = Join-Path $AssetsDir $f }
    if (-not (Test-Path $p)) { Write-Host "Optional lipsa: $f - $($optional[$f])" -ForegroundColor DarkYellow }
}

# Daca asset-urile sunt doar in build_installers\assets, le copiem in radacina ca PyInstaller sa le vada
foreach ($f in @("logo.ico","Naturen2.png","despre.gif")) {
    $inRoot = Join-Path $Root $f
    $inAssets = Join-Path $AssetsDir $f
    if (-not (Test-Path $inRoot) -and (Test-Path $inAssets)) {
        Copy-Item $inAssets -Destination $inRoot -Force
        Write-Host "Copiat $f din assets\ in radacina proiectului" -ForegroundColor Gray
    }
}

# Build Ofertare
Write-Host "`n--- Build Soft Ofertare ---" -ForegroundColor Green
python -m PyInstaller --noconfirm --clean (Join-Path $ScriptDir "specs\ofertare.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Build Admin
Write-Host "`n--- Build Soft Admin ---" -ForegroundColor Green
python -m PyInstaller --noconfirm --clean (Join-Path $ScriptDir "specs\admin.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Copiere exe si imagini in subfolder exe\
$ExeDir = Join-Path $ScriptDir "exe"
New-Item -ItemType Directory -Force -Path $ExeDir | Out-Null
Copy-Item (Join-Path $Root "dist\Soft_Ofertare.exe") -Destination $ExeDir -Force
Copy-Item (Join-Path $Root "dist\Soft_Admin.exe") -Destination $ExeDir -Force
Copy-Item (Join-Path $Root "Naturen2.png") -Destination $ExeDir -Force
Copy-Item (Join-Path $Root "logo.ico") -Destination $ExeDir -Force
$settings = Join-Path $Root "app_settings.json"
if (Test-Path $settings) {
    Copy-Item $settings -Destination $ExeDir -Force
    Write-Host "Copiat app_settings.json in exe\" -ForegroundColor Gray
}

Write-Host "`nBuild finalizat. Structura:" -ForegroundColor Green
Write-Host "  build_installers\exe\  -> Soft_Ofertare.exe, Soft_Admin.exe, Naturen2.png, logo.ico"
Write-Host "  build_installers\     -> installer_ofertare.iss, installer_admin.iss"
Write-Host "`nDeschide fiecare .iss in Inno Setup si compileaza, sau ruleaza build_installers.bat" -ForegroundColor Cyan
