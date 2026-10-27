@echo off
echo Starting SpeakPal ...
start "SpeakPal backend" cmd /c "%~dp0start-backend.bat"
timeout /t 2 >nul
start "SpeakPal frontend" cmd /c "%~dp0start-frontend.bat"
timeout /t 6 >nul
start "" "http://127.0.0.1:5173"
echo If the browser did not open, visit http://127.0.0.1:5173 manually.
echo Closing this window does NOT stop the servers. Close their windows instead.
timeout /t 3 >nul
