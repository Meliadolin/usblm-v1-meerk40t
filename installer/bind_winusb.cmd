@echo off
rem ============================================================
rem  Bind the USBLM-V1 board to WinUSB with Zadig.
rem  zadig.exe lives in tools\. Run AFTER plugging in the laser.
rem ============================================================
cd /d "%~dp0"
set "PKG=%~dp0.."
if not exist "%PKG%\logs" mkdir "%PKG%\logs"
set LOG=%PKG%\logs\bind_winusb_log.txt
echo === Bind WinUSB %date% %time% === > "%LOG%"

if not exist "%PKG%\tools\zadig.exe" (
    echo [FAIL] tools\zadig.exe missing from this package - re-extract it.
    pause
    exit /b 1
)

rem --- generate the zadig config (read at startup) + preset ---
> "%PKG%\tools\zadig.ini" echo [general]
>> "%PKG%\tools\zadig.ini" echo advanced_mode=true
>> "%PKG%\tools\zadig.ini" echo exit_on_success=true
>> "%PKG%\tools\zadig.ini" echo [device]
>> "%PKG%\tools\zadig.ini" echo list_all=true
> "%PKG%\tools\usblm-v1.ini" echo [device]
>> "%PKG%\tools\usblm-v1.ini" echo VID=9588
>> "%PKG%\tools\usblm-v1.ini" echo PID=9999
>> "%PKG%\tools\usblm-v1.ini" echo Description=USBLM-V1

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo This step needs administrator rights.
    echo A Windows permission dialog will appear - click Yes.
    echo (If it does not appear, right-click this file and choose
    echo  "Run as administrator".)
    echo [elevation requested] >> "%LOG%"
    powershell -Command "Start-Process -Verb RunAs -Wait -FilePath '%~f0'"
    exit /b 0
)
echo [OK] Elevated >> "%LOG%"

echo.
echo Starting Zadig - the signed WinUSB driver tool.
echo   A Zadig window is opening now. In it:
echo     1. Pick the board from the dropdown: "USBLM-V1"
echo        (VID 9588 - PID 9999 in normal mode, 9990 in loader mode)
echo     2. Make sure "WinUSB" is the selected driver (it is by default)
echo     3. Click "Install Driver"
echo     4. The window closes by itself when the install is done.
echo   Board missing from the dropdown? Use menu File / Open / usblm-v1.ini
echo   to pre-fill the VID/PID fields.
echo.
start "" /wait "%PKG%\tools\zadig.exe"
set EXIT=%errorlevel%
echo zadig exit code: %EXIT% >> "%LOG%"

rem --- verify: the board must now be bound to the WinUSB service ---
powershell -NoProfile -Command "if (@(Get-PnpDevice -PresentOnly -InstanceId 'USB\VID_9588*' -ErrorAction SilentlyContinue | Where-Object { $_.Service -eq 'WinUSB' -and $_.Status -eq 'OK' }).Count -gt 0) { Write-Output YES } else { Write-Output NO }" > "%TEMP%\winusb_check.txt" 2>nul
set /p OK=<"%TEMP%\winusb_check.txt"
if not defined OK set OK=NO
echo WINUSB_OK=%OK% >> "%LOG%"

echo.
echo ============================================================
if "%OK%"=="YES" (
    echo  [OK] WinUSB driver installed.
    echo  In Device Manager the board shows as "USBLM-V1" with the
    echo  WinUSB service and no warning triangle.
    echo  (Loader mode still shows "Unknown Device #1" until the
    echo   firmware upload switches it back to normal mode.)
) else (
    echo  [FAIL] The board is not bound to WinUSB yet.
    echo         Details: %LOG%
    echo         Common causes:
    echo           - Zadig was closed before "Install Driver" was clicked
    echo           - The board is not plugged in (it must be plugged in)
    echo           - The board was not picked in the dropdown
    echo         Just run this again - zadig is pre-configured.
)
echo ============================================================
echo.
echo Next: run scripts\selftest.cmd  (expect 5/5 PASS)
pause
