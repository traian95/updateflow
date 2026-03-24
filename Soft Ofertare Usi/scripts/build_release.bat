@echo off
setlocal enableextensions
cd /d "%~dp0.."
set "PROJECT_ROOT=%cd%"
set "RELEASE_ROOT=%PROJECT_ROOT%\..\v1.0.0 stabila"

echo ========================================
echo  Release build: ofertare + admin + updater
echo  Project: %PROJECT_ROOT%
echo  Output:  %RELEASE_ROOT%
echo ========================================

echo [1/8] Prepare assets folder...
if not exist "assets" mkdir "assets"
if exist "utils\assets\images" (
  xcopy /E /I /Y "utils\assets\images\*" "assets\" >nul
)
if exist "assets\logo.ico" if not exist "assets\icon.ico" copy /Y "assets\logo.ico" "assets\icon.ico" >nul

echo [2/8] Sync PNG/GIF for bundle (sync_assets_for_build.py)...
python sync_assets_for_build.py
if errorlevel 1 goto :fail

echo [3/8] Clean previous PyInstaller output...
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
if exist "dist" (
  echo WARNING: Could not remove dist\ — close ofertare.exe, admin.exe, or updater.exe if open from this folder, then run again.
  exit /b 1
)

echo [4/8] PyInstaller: ofertare.spec (onedir: dist\ofertare\ + _internal\)...
pyinstaller --noconfirm "ofertare.spec"
if errorlevel 1 goto :fail

echo [5/8] PyInstaller: admin.spec (onedir: dist\admin\ + _internal\)...
pyinstaller --noconfirm "admin.spec"
if errorlevel 1 goto :fail

echo [6/8] PyInstaller: updater.spec (onefile: dist\updater.exe)...
pyinstaller --noconfirm "updater.spec"
if errorlevel 1 goto :fail

echo [7/8] Copy updater helper next to main app onedir (dist\ofertare\)...
copy /Y "updater.py" "dist\ofertare\" >nul
if errorlevel 1 goto :fail
copy /Y "version.json" "dist\ofertare\" >nul
if errorlevel 1 goto :fail
copy /Y "dist\updater.exe" "dist\ofertare\" >nul
if errorlevel 1 goto :fail

echo [8/8] Stage files under release folder...
call :stage_release
if errorlevel 1 goto :fail

echo.
echo Done. Test main app from: dist\ofertare\ofertare.exe  (includes _internal\, updater.exe, version.json)
echo       Test admin from: dist\admin\admin.exe
echo Staged under: %RELEASE_ROOT%
goto :eof

:stage_release
mkdir "%RELEASE_ROOT%" 2>nul
mkdir "%RELEASE_ROOT%\ofertare_app" 2>nul
mkdir "%RELEASE_ROOT%\admin_app" 2>nul
mkdir "%RELEASE_ROOT%\assets" 2>nul
mkdir "%RELEASE_ROOT%\installers" 2>nul
mkdir "%RELEASE_ROOT%\scripts" 2>nul
mkdir "%RELEASE_ROOT%\docs" 2>nul

echo     Stage onedir: dist\ofertare\ -^> ofertare_app\
xcopy /E /I /Y "dist\ofertare\*" "%RELEASE_ROOT%\ofertare_app\" >nul
if errorlevel 1 exit /b 1

echo     Stage onedir: dist\admin\ -^> admin_app\
xcopy /E /I /Y "dist\admin\*" "%RELEASE_ROOT%\admin_app\" >nul
if errorlevel 1 exit /b 1

rem Overlay synced assets beside exe (paths.py also uses _internal; this keeps legacy side-by-side assets)
xcopy /E /I /Y "assets\*" "%RELEASE_ROOT%\ofertare_app\assets\" >nul
if errorlevel 1 exit /b 1
xcopy /E /I /Y "assets\*" "%RELEASE_ROOT%\admin_app\assets\" >nul
if errorlevel 1 exit /b 1

rem Optional: reference copy of icon at release root for docs/packaging
if exist "assets\icon.ico" copy /Y "assets\icon.ico" "%RELEASE_ROOT%\assets\application_icon.ico" >nul

echo     Sync Inno Setup scripts from release\installers ...
if exist "release\installers\setup_ofertare.iss" (
  xcopy /E /I /Y "release\installers\*" "%RELEASE_ROOT%\installers\" >nul
  if errorlevel 1 exit /b 1
)

echo     Remove previous compiled Setup EXEs from installers folder ...
del /Q "%RELEASE_ROOT%\installers\Naturen_Flow_*_Setup.exe" 2>nul
del /Q "%RELEASE_ROOT%\installers\Naturen_Flow_*_Update.exe" 2>nul
del /Q "%RELEASE_ROOT%\installers\Naturen_Admin_*_Setup.exe" 2>nul

echo     Copy release documentation ...
if exist "docs\RELEASE_README.md" copy /Y "docs\RELEASE_README.md" "%RELEASE_ROOT%\docs\RELEASE_README.md" >nul
if exist "RELEASE_REBUILD_REPORT.md" copy /Y "RELEASE_REBUILD_REPORT.md" "%RELEASE_ROOT%\docs\RELEASE_REBUILD_REPORT.md" >nul

copy /Y "%~dp0README_SCRIPTS.txt" "%RELEASE_ROOT%\scripts\README_SCRIPTS.txt" >nul 2>&1
if not exist "%RELEASE_ROOT%\assets\README.txt" (
  echo This folder may contain a reference copy of the application icon. > "%RELEASE_ROOT%\assets\README.txt"
  echo Authoritative assets are under ofertare_app\assets and admin_app\assets. >> "%RELEASE_ROOT%\assets\README.txt"
)
exit /b 0

:fail
echo.
echo Build failed. See errors above.
exit /b 1
