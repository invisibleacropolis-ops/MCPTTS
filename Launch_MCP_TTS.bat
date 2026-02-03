@echo off
REM MCP TTS Server Launcher
REM Double-click this file to start the GUI application

title MCP TTS Server
cd /d "%~dp0"

echo ============================================
echo   MCP TTS Server - Starting...
echo ============================================
echo.

REM 1. Check for Python 3.11 specifically via launcher or path
set "PYTHON_CMD=python"
py -3.11 -c "exit()" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.11"
    goto :check_venv
)

python --version | findstr "3.11 3.12 3.13" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_venv
)

echo WARNING: Python 3.11+ not found on PATH or via Launcher.
echo Current version is:
python --version
echo Attempting to proceed with default python...
echo.

:check_venv
REM 2. Check if virtual environment exists
if exist ".venv\Scripts\python.exe" goto :run

echo [SETUP] Virtual environment not found. 
echo [SETUP] Attempting to create it and install dependencies...

where uv >nul 2>&1
if not errorlevel 1 goto :setup_uv

:setup_standard
echo [SETUP] uv not found, using %PYTHON_CMD%...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo [SETUP] Installing dependencies (this may take a minute)...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .
goto :setup_complete

:setup_uv
echo [SETUP] Using uv for faster setup...
uv venv .venv --python 3.11
if errorlevel 1 (
    echo [SETUP] uv venv failed, trying without --python flag...
    uv venv .venv
)
uv pip install -e .
goto :setup_complete

:setup_complete
if errorlevel 1 (
    echo ERROR: Installation failed.
    pause
    exit /b 1
)
echo [SETUP] Environment ready!
echo.

:run
REM 3. Activate and run
echo Starting MCP TTS GUI...
echo.
set PYTHONPATH=%~dp0src;%PYTHONPATH%
.venv\Scripts\python.exe -m mcp_tts.main

REM Keep window open if there was an error
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
