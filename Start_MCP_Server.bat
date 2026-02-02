@echo off
REM MCP TTS Server - Server Only Mode
REM Use this for connecting from Claude Desktop or other MCP clients

title MCP TTS Server (Server Mode)
cd /d "%~dp0"

echo ============================================
echo   MCP TTS Server - Server Mode
echo ============================================
echo.
echo This runs the MCP server via stdio transport.
echo Connect from Claude Desktop or MCP Inspector.
echo.
echo Press Ctrl+C to stop the server.
echo ============================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run: uv venv ^&^& uv pip install -e .
    pause
    exit /b 1
)

set PYTHONPATH=%~dp0src;%PYTHONPATH%
.venv\Scripts\python.exe -m mcp_tts.main --server

pause
