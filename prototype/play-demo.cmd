@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-play.ps1" -Demo -Port 8766
if errorlevel 1 exit /b 1
start "" "http://127.0.0.1:8766"
