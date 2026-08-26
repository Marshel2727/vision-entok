$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "start_backend.ps1"
Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$backendScript`"" -WorkingDirectory $projectRoot -WindowStyle Hidden
Set-Location $projectRoot
docker compose up --build -d frontend
Write-Host "Backend lokal dan frontend Docker sedang dimulai. Buka http://localhost:3000"
