@echo off
set "PATH=%~dp0tools\node;%PATH%"
cd /d "%~dp0frontend"
echo Starting frontend on http://127.0.0.1:5173 ...
echo Wait for "Local: http://localhost:5173" and keep this window open.
echo.
call npm run dev
echo.
echo Frontend stopped. Press any key to close.
pause >nul
