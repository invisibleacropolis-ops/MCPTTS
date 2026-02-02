@echo off
setlocal

REM Fish Speech repo location
set "FISH_SPEECH_REPO=C:\GITHUB\FishSpeechServer"

REM API endpoint used by MCP TTS
set "FISH_SPEECH_API_URL=http://127.0.0.1:8080"

REM Choose extra for torch build: cpu, cu126, cu128, cu129
if "%FISH_SPEECH_EXTRA%"=="" set "FISH_SPEECH_EXTRA=cu128"

REM Optional: set HF cache directory if desired
REM set "HF_HOME=%USERPROFILE%\.cache\huggingface"

if not exist "%FISH_SPEECH_REPO%" (
  echo Fish Speech repo not found: %FISH_SPEECH_REPO%
  exit /b 1
)

set "LOG_DIR=%FISH_SPEECH_REPO%\logs"
set "LOG_FILE=%LOG_DIR%\fish_speech_api.log"

if not exist "%LOG_DIR%" (
  mkdir "%LOG_DIR%" >nul 2>&1
)

set "VENV_DIR=%FISH_SPEECH_REPO%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Creating venv...
  python -m venv "%VENV_DIR%"
)

if not exist "%PYTHON_EXE%" (
  echo Python venv not found: %PYTHON_EXE%
  exit /b 1
)

pushd "%FISH_SPEECH_REPO%"

REM Ensure dependencies are installed
"%PYTHON_EXE%" -c "import pyrootutils" >nul 2>&1
if errorlevel 1 (
  echo Installing Fish Speech dependencies...
  "%PYTHON_EXE%" -m pip install --upgrade pip
  "%PYTHON_EXE%" -m pip install -e ".["%FISH_SPEECH_EXTRA%"]"
)

REM Start Fish Speech API server in background
start "Fish Speech API" /b "%PYTHON_EXE%" -m tools.api_server ^
  --listen 127.0.0.1:8080 ^
  --llama-checkpoint-path "checkpoints/openaudio-s1-mini" ^
  --decoder-checkpoint-path "checkpoints/openaudio-s1-mini/codec.pth" ^
  --decoder-config-name modded_dac_vq ^
  --compile ^
  1>"%LOG_FILE%" 2>&1

REM Wait for port to be open
for /l %%i in (1,1,20) do (
  powershell -Command "(Test-NetConnection -ComputerName 127.0.0.1 -Port 8080).TcpTestSucceeded" | findstr /i "True" >nul
  if not errorlevel 1 goto ready
  timeout /t 1 >nul
)

echo Fish Speech API failed to start. Check logs at: %LOG_FILE%
popd
endlocal
exit /b 1

:ready
echo Fish Speech API is running on %FISH_SPEECH_API_URL%
popd
endlocal
