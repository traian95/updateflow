@echo off
setlocal enableextensions
cd /d "%~dp0"

echo [1/2] Building exe with PyInstaller ^(dist^)...
call build_apps.bat
if errorlevel 1 goto :fail

echo.
echo [2/2] Copying into folder 1.0.0 ^(exe + assets + version name 1.0.0^)...
if not exist "1.0.0" mkdir "1.0.0"
if not exist "1.0.0\assets" mkdir "1.0.0\assets"

copy /Y "dist\Naturen Flow 1.0.0.exe" "1.0.0\" >nul
if errorlevel 1 goto :fail
copy /Y "dist\Naturen Admin 1.0.0.exe" "1.0.0\" >nul
if errorlevel 1 goto :fail

xcopy /E /I /Y "assets\*" "1.0.0\assets\" >nul
if errorlevel 1 goto :fail
copy /Y "updater.py" "1.0.0\" >nul
if errorlevel 1 goto :fail
copy /Y "version.json" "1.0.0\" >nul
if errorlevel 1 goto :fail

echo.
echo Ready: Soft Ofertare Usi\1.0.0\
echo   - Naturen Flow 1.0.0.exe, Naturen Admin 1.0.0.exe
echo   - updater.py, version.json
echo   - assets\ ^(images^)
echo   - setup_flow.iss, setup_admin.iss, setup_flow_update.iss, compile_installers.bat
echo Next: run 1.0.0\compile_installers.bat to build Setup.exe into 1.0.0\installer\
goto :eof

:fail
echo Failed.
exit /b 1
