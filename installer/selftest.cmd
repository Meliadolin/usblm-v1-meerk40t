@echo off
rem Run selftest.py with the bundled runtime (no Python on PATH needed)
cd /d "%~dp0"
set "RUNTIME=%~dp0..\runtime"
if exist "%RUNTIME%\python.exe" (
    "%RUNTIME%\python.exe" "%~dp0..\tests\selftest.py"
) else (
    echo Bundled runtime not found. Run install.bat first.
    pause
)
