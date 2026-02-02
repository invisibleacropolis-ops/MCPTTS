@echo off
REM MCP TTS Server Launcher
REM Double-click this file to start the GUI application

title MCP TTS Server
cd /d "%~dp0"

echo ============================================
echo   MCP TTS Server - Starting...
echo ============================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run: uv venv ^&^& uv pip install -e .
    pause
    exit /b 1
)

REM Activate and run
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
