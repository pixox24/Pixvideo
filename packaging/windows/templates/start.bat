@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Pixelle-Video - Windows Launcher
echo ========================================
echo.

:: Set environment variables
set "PYTHON_HOME=%~dp0python\python311"
set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%~dp0tools\ffmpeg\bin;%PATH%"
set "PROJECT_ROOT=%~dp0Pixelle-Video"

:: Change to project directory
cd /d "%PROJECT_ROOT%"

:: Set PYTHONPATH to project root for module imports
set "PYTHONPATH=%PROJECT_ROOT%"

:: Set PIXELLE_VIDEO_ROOT environment variable for reliable path resolution
set "PIXELLE_VIDEO_ROOT=%PROJECT_ROOT%"

:: Start FastAPI with the bundled React workbench
echo [Starting] Launching Pixelle-Video...
echo Open http://127.0.0.1:8000 in your browser.
echo.
echo Note: Configure API keys and settings in the React workbench.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

"%PYTHON_HOME%\python.exe" api\app.py --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Please check:
    echo   1. Python is properly installed
    echo   2. Dependencies are installed
    echo.
    pause
)
