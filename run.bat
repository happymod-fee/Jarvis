@echo off
setlocal
title VAX Voice Assistant Launcher

echo ===================================================
echo     VAX Voice Assistant (Windows Launcher)
echo ===================================================
echo.

cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please install Python 3.11 or higher and add it to PATH.
    pause
    exit /b 1
)

:: Ensure dependencies are installed
echo [INFO] Verifying core environment...
python -c "import PySide6, sounddevice, openwakeword" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required dependencies...
    pip install -r "%~dp0requirements.txt"
)

:: Launch VAX
echo [INFO] Starting VAX Voice Assistant...
start /b python "%~dp0main.py" %*
echo [INFO] VAX is running in the background. Check your system tray or desktop overlay.
exit /b 0
