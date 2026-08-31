@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment tidak ditemukan di .venv.
    echo Buat environment lalu pasang requirements\runtime.txt.
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m entok_vision.desktop %*
if errorlevel 1 pause
