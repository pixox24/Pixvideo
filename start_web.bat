@echo off
chcp 65001 >nul 2>&1
setlocal

cd /d "%~dp0"

set "PROJECT_ROOT=%CD%"
set "VENV_PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "VENV_SCRIPTS=%PROJECT_ROOT%\.venv\Scripts"
set "FFMPEG_BIN=%PROJECT_ROOT%\.tools\ffmpeg\bin"

echo ========================================
echo   Pixelle-Video React Workbench
echo ========================================
echo.

if not exist "%VENV_PY%" (
    echo [SETUP] Local .venv was not found. Creating it with Python 3.12...
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Python 3.12 was not found.
        echo Install Python 3.12, then run this script again.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing Python dependencies. This can take a few minutes...
    "%VENV_PY%" -m ensurepip --upgrade
    "%VENV_PY%" -m pip install -e .
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
)

if not exist "config.yaml" (
    if exist "config.example.yaml" (
        echo [SETUP] Creating config.yaml from config.example.yaml...
        copy /Y "config.example.yaml" "config.yaml" >nul
    )
)

if not exist "%FFMPEG_BIN%\ffmpeg.exe" (
    echo [WARN] ffmpeg.exe was not found at:
    echo        %FFMPEG_BIN%\ffmpeg.exe
    echo        Video composition will fail until FFmpeg is installed.
    echo.
)

set "PATH=%VENV_SCRIPTS%;%FFMPEG_BIN%;%PATH%"
set "PYTHONPATH=%PROJECT_ROOT%"
set "PIXELLE_VIDEO_ROOT=%PROJECT_ROOT%"

where npm >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] npm was not found. Install Node.js 22+ and run this script again.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [SETUP] Installing frontend dependencies...
    pushd frontend
    call npm ci
    if errorlevel 1 (
        popd
        echo.
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
    popd
)

echo [BUILD] Building React workbench...
pushd frontend
call npm run build
if errorlevel 1 (
    popd
    echo.
    echo [ERROR] Failed to build the React workbench.
    pause
    exit /b 1
)
popd

echo [START] Web UI and API: http://127.0.0.1:8000
echo Press Ctrl+C to stop the server.
echo.

"%VENV_PY%" api\app.py --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo [ERROR] Pixelle-Video failed to start.
    pause
    exit /b 1
)
