@echo off
REM Fully automatic one-time setup for Dafter on Windows.
REM Installs Python + Ollama if missing, downloads the AI models, installs Python packages.
cd /d "%~dp0"
setlocal
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Ollama;%PATH%"
echo Setup started %DATE% %TIME% > setup.log

echo === [1/5] Python ===
python -c "import sys; print(sys.version)" 2>nul
if errorlevel 1 (
  echo Installing Python 3.12...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
)
python -c "import sys; print(sys.version)" || (echo PYTHON MISSING >> setup.log & echo Python could not be installed. & pause & exit /b 1)
echo Python OK >> setup.log

echo.
echo === [2/5] Ollama ===
ollama --version 2>nul
if errorlevel 1 (
  echo Installing Ollama...
  winget install -e --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
)
ollama --version || (echo OLLAMA MISSING >> setup.log & echo Ollama could not be installed. & pause & exit /b 1)
echo Ollama OK >> setup.log

REM Make sure the Ollama server is running
curl -s http://127.0.0.1:11434 >nul 2>nul
if errorlevel 1 (
  start "" /min ollama serve
  timeout /t 6 /nobreak >nul
)

echo.
echo === [3/5] Chat model qwen2.5:1.5b (about 1 GB) ===
ollama pull qwen2.5:1.5b || (echo CHAT MODEL FAILED >> setup.log & pause & exit /b 1)
echo Chat model OK >> setup.log

echo.
echo === [4/5] Photo-verification model qwen2.5vl:3b (about 3 GB) ===
ollama pull qwen2.5vl:3b && (echo Vision model OK >> setup.log) || (echo VISION MODEL FAILED >> setup.log)

echo.
echo === [5/5] Python packages ===
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt || (echo PIP FAILED >> setup.log & pause & exit /b 1)
echo Packages OK >> setup.log
if not exist .env copy .env.example .env >nul
ollama list | find "qwen2.5vl:3b" >nul && powershell -NoProfile -Command "(Get-Content .env) -replace '^OLLAMA_VISION_MODEL=.*','OLLAMA_VISION_MODEL=qwen2.5vl:3b' | Set-Content .env"

echo SETUP COMPLETE >> setup.log
echo.
echo Setup complete. Starting Dafter...
call run.bat
