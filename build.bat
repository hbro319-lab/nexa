@echo off
REM ============================================================
REM  NEXA v2.0 — Windows Build Script
REM  Creates nexa.exe using PyInstaller
REM ============================================================
echo.
echo  ===================================
echo   NEXA v2.0 — Building Windows .exe
echo  ===================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

REM Clean previous build
echo [2/3] Cleaning previous build...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

REM Build
echo [3/3] Building nexa.exe...
pyinstaller nexa.spec

if exist "dist\nexa.exe" (
    echo.
    echo  ===================================
    echo   BUILD SUCCESSFUL!
    echo   Output: dist\nexa.exe
    echo  ===================================
    echo.
    echo  Usage:
    echo    dist\nexa.exe                   Interactive CLI
    echo    dist\nexa.exe --server          Start dispatch server
    echo    dist\nexa.exe --gui             Open web UI + server
    echo    dist\nexa.exe --search "chrome" Search installed apps
    echo.
    echo  Everything is embedded in the .exe — no extra files needed!
    echo  Just run nexa.exe from anywhere.
    echo.
) else (
    echo.
    echo  [ERROR] Build failed. Check the output above for errors.
    echo.
)

pause
