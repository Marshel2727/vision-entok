@echo off
setlocal
cd /d "%~dp0back_end"

if not exist "venv\Scripts\python.exe" (
    echo Python virtual environment tidak ditemukan di back_end\venv.
    echo Jalankan instalasi dependency backend terlebih dahulu.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" "ai\cctv_gui.py"
if errorlevel 1 pause
