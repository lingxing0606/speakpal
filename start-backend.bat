@echo off
cd /d "%~dp0backend"

netstat -ano | findstr "127.0.0.1:8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo Backend is already running on port 8000.
  echo Open http://127.0.0.1:8000/ in your browser.
  echo To restart it, close the existing backend window first.
  pause
  exit /b 0
)

echo Starting backend on http://127.0.0.1:8000 ...
echo Wait for "Uvicorn running" and keep this window open.
echo.
"%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo Backend stopped. Press any key to close.
pause >nul
