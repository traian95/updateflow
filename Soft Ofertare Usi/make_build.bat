@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Stergere build\ si dist\...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [2/4] PyInstaller --noconfirm NaturenFlow.spec (onedir: NaturenFlow.exe + updater.exe)...
py -3 -m PyInstaller --noconfirm NaturenFlow.spec
if errorlevel 1 exit /b 1

echo [3/4] Copiere assets\ si version.json lângă exe (resurse onedir lângă get_resource_path)...
if not exist "dist\NaturenFlow\assets" mkdir "dist\NaturenFlow\assets"
if exist "assets\*" xcopy /E /I /Y "assets\*" "dist\NaturenFlow\assets\" >nul
copy /Y "version.json" "dist\NaturenFlow\version.json" >nul

echo [4/4] Deschidere dist\NaturenFlow pentru inspectie...
start "" explorer "dist\NaturenFlow"
endlocal
