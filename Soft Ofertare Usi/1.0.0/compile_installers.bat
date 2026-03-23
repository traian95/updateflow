@echo off
setlocal enableextensions
cd /d "%~dp0"

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
  echo Inno Setup 6 ^(ISCC.exe^) not found.
  echo Install from https://jrsoftware.org/isdl.php
  exit /b 1
 )

if not exist "Naturen Flow 1.0.0.exe" (
  echo Missing: Naturen Flow 1.0.0.exe — run prepare_release_1.0.0.bat from parent folder first.
  exit /b 1
)
if not exist "Naturen Admin 1.0.0.exe" (
  echo Missing: Naturen Admin 1.0.0.exe — run prepare_release_1.0.0.bat from parent folder first.
  exit /b 1
)
if not exist "assets\icon.ico" (
  echo Missing: assets\ — run prepare_release_1.0.0.bat from parent folder first.
  exit /b 1
)

echo Compiling setup_flow.iss ...
"%ISCC%" "setup_flow.iss"
if errorlevel 1 goto :fail

echo Compiling setup_admin.iss ...
"%ISCC%" "setup_admin.iss"
if errorlevel 1 goto :fail

echo Compiling setup_flow_update.iss ...
"%ISCC%" "setup_flow_update.iss"
if errorlevel 1 goto :fail

echo.
echo Output: %cd%\installer\
goto :eof

:fail
echo Inno compile failed.
exit /b 1
