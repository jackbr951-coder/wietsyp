@echo off
REM One-click start for Windows. Creates the virtual environment on first run.
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv || py -m venv .venv )
call .venv\Scripts\activate.bat
if not exist .env copy .env.example .env >nul
python -m pip install -q -r requirements.txt
echo.
echo Dafter is starting at http://127.0.0.1:8000
start "Dafter Server" "%CD%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000"
