param(
    [string]$PythonExecutable = ".\.venv\Scripts\python.exe",
    [ValidateSet("auto", "cpu", "0")]
    [string]$Device = "auto"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    & $PythonExecutable -m training.evaluate_models --device $Device
    if ($LASTEXITCODE -eq 3) {
        throw "Kandidat tidak lulus gate evaluasi. Model aplikasi tidak diubah."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Evaluasi gagal dengan exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
