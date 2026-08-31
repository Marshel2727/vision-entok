param(
    [string]$PythonExecutable = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    & $PythonExecutable -m training.promote_model
    if ($LASTEXITCODE -ne 0) {
        throw "Promosi model ditolak atau gagal dengan exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
