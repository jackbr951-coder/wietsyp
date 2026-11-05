@echo off
REM Downloads the photo-verification model, retrying automatically when the internet drops.
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
set MODEL=qwen3-vl:2b
set TRY=0
echo Vision setup started %DATE% %TIME% > vision.log
:again
set /a TRY+=1
echo.
echo === Downloading %MODEL% - attempt %TRY% - progress is kept between attempts ===
ollama pull %MODEL%
if not errorlevel 1 goto done
echo Attempt %TRY% failed %TIME% >> vision.log
if %TRY% GEQ 300 goto failed
echo Connection problem - retrying in 15 seconds...
timeout /t 15 /nobreak
goto again
:failed
echo VISION DOWNLOAD FAILED >> vision.log
echo Download failed after many attempts - check your internet and run get-vision.bat again.
pause
exit /b 1
:done
echo Downloaded %MODEL% >> vision.log
powershell -NoProfile -Command "(Get-Content .env) -replace '^OLLAMA_VISION_MODEL=.*','OLLAMA_VISION_MODEL=%MODEL%' | Set-Content .env"
echo VISION READY >> vision.log
call restart.bat
