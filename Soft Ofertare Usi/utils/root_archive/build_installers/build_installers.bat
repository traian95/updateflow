@echo off
REM Compileaza cele doua instalatoare (Inno Setup).
REM Ruleaza din folderul build_installers. Trebuie sa ai deja: Soft_Ofertare.exe, Soft_Admin.exe, Naturen2.png, logo.ico

set "ISCC=iscc"
where iscc >nul 2>&1
if errorlevel 1 (
  set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

cd /d "%~dp0"
echo Compilare installer Ofertare...
"%ISCC%" "installer_ofertare.iss"
if errorlevel 1 exit /b 1
echo Compilare installer Admin...
"%ISCC%" "installer_admin.iss"
if errorlevel 1 exit /b 1
echo.
echo Gata. Setup-uri generate in acest folder:
dir /b NaturenFlow_*.exe 2>nul
pause
