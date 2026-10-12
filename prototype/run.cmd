@echo off
setlocal
cd /d "%~dp0"
set "LIFE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%LIFE_PYTHON%" goto run
set "LIFE_PYTHON=python"
:run
"%LIFE_PYTHON%" -X utf8 -B -m lifebox.cli %*
exit /b %errorlevel%
