@echo off
REM Stops any running Dafter server on port 8000, then starts it again.
cd /d "%~dp0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%p /F
timeout /t 1 /nobreak
call run.bat
