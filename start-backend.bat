@echo off
setlocal

for /f "tokens=5" %%a in ('netstat -ano ^| findstr "127.0.0.1:8000" ^| findstr "LISTENING"') do (
  echo Stopping old backend on port 8000 ^(PID %%a^) ...
  taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 >nul

netstat -ano | findstr "127.0.0.1:8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo Port 8000 is still in use. Close the old backend window and try again.
  netstat -ano | findstr "127.0.0.1:8000"
  pause
  exit /b 1
)

cd /d "%~dp0backend"
echo Starting backend on http://127.0.0.1:8000 ...
echo Wait for "Uvicorn running" and keep this window open.
echo.
"%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo Backend stopped. Press any key to close.
pause >nul
