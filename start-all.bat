@echo off
echo Starting SpeakPal ...
echo.

start "SpeakPal BACKEND" cmd /k "%~dp0start-backend.bat"
timeout /t 2 >nul
start "SpeakPal FRONTEND" cmd /k "%~dp0start-frontend.bat"
timeout /t 8 >nul

start "" "http://127.0.0.1:5173"

echo.
echo Two windows should be open:
echo   SpeakPal BACKEND  =^> http://127.0.0.1:8000
echo   SpeakPal FRONTEND =^> http://127.0.0.1:5173
echo If you only see one, look for the other in the taskbar.
timeout /t 5 >nul
