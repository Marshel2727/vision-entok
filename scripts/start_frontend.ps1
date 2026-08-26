$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot "front_end")
if (-not (Test-Path ".\node_modules")) { npm.cmd install }
if (-not (Test-Path ".\.next")) { npm.cmd run build }
npm.cmd run start
