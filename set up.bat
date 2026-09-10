@echo off
setlocal
cd /d "%~dp0"
title Campus C Debugger - Setup
set "CAMPUS_INSTALL_DIR=%~dp0"
set "CAMPUS_PY=python"
python -c "import sys; assert sys.version_info.major == 3" >nul 2>&1
if not errorlevel 1 goto python_ready
set "CAMPUS_PY=py -3"
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto failed

:python_ready
echo [1/3] Preparing build tools...
%CAMPUS_PY% -m pip install pyinstaller > setup.log 2>&1
if errorlevel 1 goto failed
echo [2/3] Building application in this folder...
if not exist ".setup-work" mkdir ".setup-work"
%CAMPUS_PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name CampusC-Debugger --distpath . --workpath ".setup-work\build" --specpath ".setup-work" app.py >> setup.log 2>&1
if errorlevel 1 goto failed
if not exist "CampusC-Debugger.exe" goto failed
echo [3/3] Creating desktop shortcut...
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $d=[Environment]::GetFolderPath('DesktopDirectory'); if ([string]::IsNullOrWhiteSpace($d)) { throw 'Desktop unavailable' }; $exe=Join-Path $env:CAMPUS_INSTALL_DIR 'CampusC-Debugger.exe'; $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'Campus C Debugger.lnk')); $s.TargetPath=$exe; $s.WorkingDirectory=$env:CAMPUS_INSTALL_DIR; $s.IconLocation=$exe+',0'; $s.Save()" >> setup.log 2>&1
if errorlevel 1 goto failed
echo Setup complete.
exit /b 0

:failed
echo Setup failed. Check setup.log. Python 3 and Internet access are required.
echo If PowerShell reports a policy restriction, contact your administrator.
pause
exit /b 1
