@echo off
setlocal enableextensions
cd /d "%~dp01.0.0"
if not exist "setup_flow.iss" (
  echo Folder 1.0.0 not found or incomplete. Run prepare_release_1.0.0.bat first.
  exit /b 1
)
call compile_installers.bat
