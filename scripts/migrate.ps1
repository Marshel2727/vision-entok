$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot "back_end")
& ".\venv\Scripts\python.exe" -m alembic upgrade head
