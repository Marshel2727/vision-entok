$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "..\packaging\windows\build_all.ps1")
