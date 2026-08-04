@echo off
rem Launch MeerK40t with the USBLM-V1 profile - NO console, NO admin.
rem The app files run in place from the package's app\ folder.
rem Output goes to logs\meerk_trace.log.
cd /d "%~dp0"
set "PKG=%~dp0.."
set "RUNTIME=%PKG%\runtime"

if exist "%RUNTIME%\pythonw.exe" (
    if exist "%PKG%\app\run_meerk40t.py" (
        start "" "%RUNTIME%\pythonw.exe" "%PKG%\app\run_meerk40t.py"
        exit /b 0
    )
    echo App files not found. Run install.bat first.
    pause
    exit /b 1
)

where pythonw >nul 2>&1
if errorlevel 1 (
    echo pythonw not found. Run install.bat first.
    pause
    exit /b 1
)
if exist "%PKG%\app\run_meerk40t.py" (
    start "" pythonw.exe "%PKG%\app\run_meerk40t.py"
    exit /b 0
)
echo App files not found. Run install.bat first.
pause
exit /b 1
