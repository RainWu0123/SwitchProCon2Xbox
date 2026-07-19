@echo off
chcp 65001 >nul 2>&1

:: ─── Request Admin Privileges ───
:: HidHide requires admin to hide the physical controller from games.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   [INFO] Requesting administrator privileges for HidHide...
    echo   [INFO] If a UAC dialog appears, please click "Yes".
    echo.

    :: Create a temporary VBS script to elevate with proper working directory
    echo Set UAC = CreateObject^("Shell.Application"^) > "%~dp0_elevate.vbs"
    echo UAC.ShellExecute "cmd.exe", "/c cd /d ""%~dp0"" && ""%~f0""", "", "runas", 1 >> "%~dp0_elevate.vbs"
    cscript //nologo "%~dp0_elevate.vbs"
    del /q "%~dp0_elevate.vbs" 2>nul
    exit /b
)

:: If we get here, we ARE admin
title Switch -> Xbox Controller Translator (Admin)

echo.
echo   +----------------------------------------------+
echo   ^|  Switch -^> Xbox Controller Translator        ^|
echo   ^|  Running as Administrator (HidHide active)   ^|
echo   +----------------------------------------------+
echo.

cd /d "%~dp0"

:: Ensure venv exists and has a working Python
if not exist "venv\Scripts\python.exe" (
    echo   [SETUP] Creating virtual environment...
    where python >nul 2>&1
    if errorlevel 1 (
        echo   [ERROR] Python is not installed or not in PATH.
        echo   Please install Python 3.8+ from https://python.org
        echo.
        pause
        exit /b 1
    )
    python -m venv venv
    if errorlevel 1 (
        echo   [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    set NEED_INSTALL=1
) else (
    set NEED_INSTALL=0
)

:: Verify critical packages; reinstall if missing (repairs half-broken venv)
.\venv\Scripts\python.exe -c "import hid, vgamepad" >nul 2>&1
if errorlevel 1 set NEED_INSTALL=1

if "%NEED_INSTALL%"=="1" (
    echo   [SETUP] Installing / repairing dependencies...
    .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo   [ERROR] pip install failed. Check requirements.txt and network.
        pause
        exit /b 1
    )
    echo   [SETUP] Done!
    echo.
)

:run
:: Already elevated by this bat — main.py will not need a second UAC for HidHide
echo   [START] Launching translator...
echo.
.\venv\Scripts\python.exe -u main.py %*

:: Keep window open on exit so user can see messages
echo.
echo   Press any key to exit...
pause >nul
