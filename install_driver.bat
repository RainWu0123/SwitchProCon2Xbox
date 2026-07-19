@echo off
title ViGEmBus Driver Installer Helper

echo.
echo   ==================================================
echo     ViGEmBus Virtual Controller Driver Installer
echo   ==================================================
echo.
echo   We have downloaded the official installer for you:
echo   - File: ViGEmBus_1.21.442.exe
echo.
echo   [INSTRUCTIONS]
echo   This tool will launch the official ViGEmBus setup wizard.
echo   If a Windows User Account Control (UAC) prompt appears, 
echo   please click "Yes" to authorize the installation.
echo.
echo   Press any key to start the installer...
pause >nul

if not exist "ViGEmBus_1.21.442.exe" (
    echo   [ERROR] Installer not found in this directory!
    pause
    exit /b 1
)

echo.
echo   [RUN] Launching setup wizard... Please complete the installation.
start "" "ViGEmBus_1.21.442.exe"

echo.
echo   ==================================================
echo   * IMPORTANT: We HIGHLY recommend RESTARTING your 
echo     computer after the installation finishes!
echo   ==================================================
echo.
echo   Setup launched successfully. You can close this window now.
echo   Press any key to exit...
pause >nul
