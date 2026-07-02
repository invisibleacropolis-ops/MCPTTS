@echo off
setlocal
REM MCP TTS Server CUDA Launcher
REM Double-click this file to start the GUI with CUDA/GPU dependencies.

title MCP TTS Server CUDA
cd /d "%~dp0"

echo ============================================
echo   MCP TTS Server - CUDA Mode Starting...
echo ============================================
echo.

REM Select the engine that can use local GPU acceleration.
set "MCP_TTS_ENGINE=piper"

REM Keep CUDA dependencies isolated from the regular CPU/cloud launcher.
set "VENV_DIR=.venv-cuda"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

REM Override this before launching if you need a different PyTorch CUDA wheel index.
REM Examples: cu121, cu124, cu126, cu128
if "%MCP_TTS_CUDA_INDEX_URL%"=="" (
    set "MCP_TTS_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128"
)

REM 1. Check for Python 3.11+ via launcher or PATH.
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
if exist "%PYTHON_EXE%" goto :check_cuda_packages

echo [SETUP] CUDA virtual environment not found.
echo [SETUP] Creating %VENV_DIR%...

where uv >nul 2>&1
if not errorlevel 1 goto :setup_uv

:setup_standard
echo [SETUP] uv not found, using %PYTHON_CMD%...
%PYTHON_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to create CUDA virtual environment.
    pause
    exit /b 1
)
goto :install_standard

:setup_uv
echo [SETUP] Using uv for faster setup...
uv venv "%VENV_DIR%" --python 3.11
if errorlevel 1 (
    echo [SETUP] uv venv failed, trying without --python flag...
    uv venv "%VENV_DIR%"
)
if errorlevel 1 (
    echo ERROR: Failed to create CUDA virtual environment.
    pause
    exit /b 1
)
goto :install_uv

:check_cuda_packages
"%PYTHON_EXE%" -c "import torch, onnxruntime; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if not errorlevel 1 goto :run

echo [SETUP] CUDA dependencies missing or CUDA is not visible.
echo [SETUP] Installing/reinstalling CUDA-enabled dependencies...

where uv >nul 2>&1
if not errorlevel 1 goto :install_uv
goto :install_standard

:install_uv
echo [SETUP] Installing PyTorch CUDA wheels from:
echo [SETUP]   %MCP_TTS_CUDA_INDEX_URL%
uv pip install --python "%PYTHON_EXE%" torch torchaudio --index-url "%MCP_TTS_CUDA_INDEX_URL%"
if errorlevel 1 goto :install_failed

echo [SETUP] Installing MCP TTS with Piper and GPU extras...
uv pip install --python "%PYTHON_EXE%" -e ".[full]"
if errorlevel 1 goto :install_failed
goto :setup_complete

:install_standard
echo [SETUP] Installing dependencies with pip...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :install_failed

echo [SETUP] Installing PyTorch CUDA wheels from:
echo [SETUP]   %MCP_TTS_CUDA_INDEX_URL%
"%PYTHON_EXE%" -m pip install torch torchaudio --index-url "%MCP_TTS_CUDA_INDEX_URL%"
if errorlevel 1 goto :install_failed

echo [SETUP] Installing MCP TTS with Piper and GPU extras...
"%PYTHON_EXE%" -m pip install -e ".[full]"
if errorlevel 1 goto :install_failed
goto :setup_complete

:install_failed
echo.
echo ERROR: CUDA dependency installation failed.
echo Check that your NVIDIA driver supports the selected CUDA wheel index:
echo   %MCP_TTS_CUDA_INDEX_URL%
pause
exit /b 1

:setup_complete
echo [SETUP] CUDA environment ready.
echo.

:run
echo [CHECK] Verifying CUDA visibility...
"%PYTHON_EXE%" -c "import torch; print('Torch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('CUDA version:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not available')"
if errorlevel 1 (
    echo ERROR: CUDA verification failed.
    pause
    exit /b 1
)

echo.
echo Starting MCP TTS GUI in CUDA mode...
echo Engine: %MCP_TTS_ENGINE%
echo Environment: %VENV_DIR%
echo.

set PYTHONPATH=%~dp0src;%PYTHONPATH%
"%PYTHON_EXE%" -m mcp_tts.main

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)

endlocal
