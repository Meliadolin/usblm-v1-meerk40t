@echo off
rem ============================================================
rem  MeerK40t + USBLM-V1 - ONE-CLICK install
rem  Everything needed is in this folder: bundled Python, all
rem  packages, drivers. No system Python needed.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PKG=%~dp0.."
set "LOG=%PKG%\logs\install_log.txt"
set "RUNTIME=%PKG%\runtime"
if not exist "%PKG%\logs" mkdir "%PKG%\logs"
echo ===== Install %date% %time% ===== > "%LOG%"

echo ============================================
echo  BJJCZ USBLM-V1 + MeerK40t installer
echo  (everything is in this folder)
echo ============================================
echo.

:: ---------- 1. Deploy bundled Python runtime ----------
echo [1/5] Deploying bundled Python runtime...
if not exist "%RUNTIME%\python.exe" (
    echo       Extracting embedded Python to %RUNTIME%...
    echo [%time%] extracting runtime >> "%LOG%"
    powershell -Command "Expand-Archive -Force '%PKG%\offline\python-embed.zip' '%RUNTIME%'"
    rem enable site-packages in the embedded python (_pth file)
    echo python312.zip> "%RUNTIME%\python312._pth"
    echo .>> "%RUNTIME%\python312._pth"
    echo Lib>> "%RUNTIME%\python312._pth"
    echo site-packages>> "%RUNTIME%\python312._pth"
    echo import site>> "%RUNTIME%\python312._pth"
)
if not exist "%RUNTIME%\python.exe" (
    echo [FAIL] Runtime extraction failed
    echo [%time%] FAIL: runtime extract >> "%LOG%"
    pause
    exit /b 1
)
echo [OK] Python runtime ready at %RUNTIME%
echo [%time%] runtime ready >> "%LOG%"
echo.

:: ---------- 2. Install Python packages ----------
echo [2/5] Installing packages from this folder...
echo       ~45 MB - takes 1-3 minutes
if not exist "%RUNTIME%\Scripts\pip.exe" (
    echo       Installing pip...
    "%RUNTIME%\python.exe" "%PKG%\offline\get-pip.py" --no-warn-script-location >> "%LOG%" 2>&1
)
"%RUNTIME%\python.exe" -m pip install --no-index --no-warn-script-location --find-links "%PKG%\offline\wheelhouse" meerk40t "wxPython==4.2.2" ezdxf pillow pyusb libusb numpy >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [FAIL] Package install failed - see logs\install_log.txt
    echo [%time%] FAIL: pip install >> "%LOG%"
    pause
    exit /b 1
)
"%RUNTIME%\python.exe" -c "import wx, usb.core, meerk40t" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Package verification failed
    echo [%time%] FAIL: import check >> "%LOG%"
    pause
    exit /b 1
)
echo [OK] Packages installed and verified
echo [%time%] packages OK >> "%LOG%"
echo.

:: ---------- 3. Deploy pre-configured MeerK40t settings ----------
echo [3/5] Deploying MeerK40t device settings (Galvo-Fiber)...
if not exist "%LOCALAPPDATA%\MeerK40t" mkdir "%LOCALAPPDATA%\MeerK40t"
if not exist "%LOCALAPPDATA%\MeerK40t\MeerK40t.cfg" (
    copy /y "%PKG%\config\MeerK40t.cfg" "%LOCALAPPDATA%\MeerK40t\MeerK40t.cfg" >nul
    echo [OK] Device settings deployed (30%% power defaults, fiber)
) else (
    echo [SKIP] Existing settings kept
)
echo [%time%] config deployed >> "%LOG%"
echo.

:: ---------- 4. WinUSB driver (optional - see STEPS.md) ----------
echo [4/5] Installing the WinUSB driver (zadig - the signed tool in tools\)...
echo       The board will re-enumerate (briefly disappear and reappear
echo       in Device Manager) - that is NORMAL.
net session >nul 2>&1
if %errorlevel% equ 0 (
    if exist "%PKG%\tools\zadig.exe" (
        > "%PKG%\tools\zadig.ini" echo [general]
        >> "%PKG%\tools\zadig.ini" echo advanced_mode=true
        >> "%PKG%\tools\zadig.ini" echo exit_on_success=true
        >> "%PKG%\tools\zadig.ini" echo [device]
        >> "%PKG%\tools\zadig.ini" echo list_all=true
        > "%PKG%\tools\usblm-v1.ini" echo [device]
        >> "%PKG%\tools\usblm-v1.ini" echo VID=9588
        >> "%PKG%\tools\usblm-v1.ini" echo PID=9999
        >> "%PKG%\tools\usblm-v1.ini" echo Description=USBLM-V1
        echo       A Zadig window opens: pick "USBLM-V1" (VID 9588) in
        echo       the dropdown, click "Install Driver" - the window
        echo       closes by itself when the install is done.
        start "" /wait "%PKG%\tools\zadig.exe"
        set "PEXIT=!errorlevel!"
        echo [%time%] zadig exit code: !PEXIT! >> "%LOG%"
        echo [OK] Done - if the window was closed without clicking
        echo      Install Driver, run scripts\bind_winusb.cmd to retry.
    ) else (
        echo [WARN] tools\zadig.exe missing - run scripts\bind_winusb.cmd later.
        echo [%time%] WinUSB skipped (zadig.exe missing) >> "%LOG%"
    )
) else (
    echo [SKIP] Not running as administrator - run scripts\bind_winusb.cmd for the driver
    echo [%time%] WinUSB skipped (not elevated) >> "%LOG%"
)
echo.

:: ---------- 5. Desktop shortcut ----------
echo [5/5] Creating the desktop shortcut...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\MeerK40t V1.lnk'); $sc.TargetPath = '%RUNTIME%\pythonw.exe'; $sc.Arguments = '"'"'%PKG%\app\run_meerk40t.py'"'"'; $sc.WorkingDirectory = '%PKG%\app'; $sc.Description = 'MeerK40t - BJJCZ USBLM-V1 laser'; $sc.Save()"
echo [OK] "MeerK40t V1" shortcut created (keep this folder where it is)
echo [%time%] shortcut created >> "%LOG%"
echo.

echo ============================================
echo  INSTALL FINISHED - next steps:
echo
echo  1. Plug in the laser
echo  2. Run scripts\bind_winusb.cmd  (or see STEPS.md)
echo  3. Run scripts\selftest.cmd     (expect 5/5 PASS)
echo  4. Double-click "MeerK40t V1" and mark!
echo ============================================
echo Full log: %LOG%
pause
