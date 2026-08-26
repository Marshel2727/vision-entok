@echo off
setlocal
cd /d "%~dp0back_end"

if not exist "venv\Scripts\python.exe" (
    echo Python virtual environment tidak ditemukan di back_end\venv.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" "ai\train.py" --config "ai\configs\train_datav2_normal_only.yaml"
pause
