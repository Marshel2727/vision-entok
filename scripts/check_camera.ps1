$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment tidak ditemukan: $pythonPath"
}
$env:PYTHONPATH = Join-Path $projectRoot "src"
& $pythonPath -m entok_vision.desktop --check-only
