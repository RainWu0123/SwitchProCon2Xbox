@echo off
:: ============================================================
:: 恢復手把可見性 (Unhide Controller)
:: 解除 HidHide 的隱藏狀態，讓 Steam Input 可以偵測到手把
:: ============================================================

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 正在請求管理員權限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Get the directory of this batch file
cd /d "%~dp0"

:: Activate venv and run unhide command
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python main.py --unhide

echo.
pause
