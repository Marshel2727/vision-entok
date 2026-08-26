$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "build_variant.ps1") -Variant CPU
& (Join-Path $PSScriptRoot "build_variant.ps1") -Variant GPU-CUDA124
