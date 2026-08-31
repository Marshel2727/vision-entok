$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment tidak ditemukan: $pythonPath"
}
$env:PYTHONPATH = "$(Join-Path $projectRoot 'src');$projectRoot"
& $pythonPath -m training.train --config (Join-Path $projectRoot "training\configs\train_datav1_v2_yolo26s.yaml") @args
