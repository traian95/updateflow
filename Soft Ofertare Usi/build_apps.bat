@echo off
setlocal enableextensions
cd /d "%~dp0"

echo [1/5] Pregatesc folderul assets...
if not exist "assets" mkdir "assets"
if exist "utils\assets\images" (
  xcopy /E /I /Y "utils\assets\images\*" "assets\" >nul
)

if exist "assets\logo.ico" if not exist "assets\icon.ico" copy /Y "assets\logo.ico" "assets\icon.ico" >nul

echo [1b/5] Sync PNG/GIF pentru bundle (customer, istoric, logout, imagini, despre.gif)...
python sync_assets_for_build.py
if errorlevel 1 goto :fail

echo [2/5] Curata build-uri anterioare...
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"

echo [3/5] Build Naturen Flow 1.0.0 (spec)...
pyinstaller --noconfirm "Naturen Flow 1.0.0.spec"
if errorlevel 1 goto :fail

echo [4/5] Build Naturen Admin 1.0.0 (spec)...
pyinstaller --noconfirm "Naturen Admin 1.0.0.spec"
if errorlevel 1 goto :fail

echo.
echo [5/5] Build finalizat. Executabilele sunt in folderul dist.
goto :eof

:fail
echo.
echo Build esuat. Verifica erorile de mai sus.
exit /b 1
