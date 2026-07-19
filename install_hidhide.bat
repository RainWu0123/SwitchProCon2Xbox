@echo off
title HidHide Driver Installer Helper

echo.
echo   ==================================================
echo     HidHide Kernel-Level Controller Blocker Installer
echo   ==================================================
echo.
echo   We have downloaded the official installer for you:
echo   - File: HidHide_Setup.exe
echo.
echo   [INSTRUCTIONS]
echo   This tool will launch the official HidHide setup wizard.
echo   This driver will hide your physical controller from games,
echo   completely curing the "flickering between keyboard and gamepad" issue!
echo.
echo   Press any key to start the installer...
pause >nul

if not exist "HidHide_Setup.exe" (
    echo   [ERROR] Installer not found in this directory!
    pause
    exit /b 1
)

echo.
echo   [RUN] Launching setup wizard... Please complete the installation.
start "" "HidHide_Setup.exe"

echo.
echo   ==================================================
echo   * IMPORTANT: You MUST RESTART your computer 
echo     after the installation finishes!
echo   ==================================================
echo.
echo   [HOW TO CONFIGURE HIDHIDE AFTER REBOOT]
echo   1. Open "HidHide Configuration Client" from Windows Start Menu.
echo   2. Under the "Devices" tab, find "If_Hid" and check the box (it will show a red lock).
echo   3. At the bottom, check "Enable device hiding".
echo   4. Now games will ONLY see the virtual Xbox 360 controller.
echo      No more keyboard/gamepad switching conflicts!
echo.
echo   Press any key to exit...
pause >nul
