param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$releaseDir = Join-Path $projectRoot "artifacts\release\0.2.0"
$base = $BaseUrl.TrimEnd("/")
$variants = [ordered]@{}
foreach ($variant in @("CPU", "GPU-CUDA124")) {
    $baseName = "EntokVisionLite-0.2.0-Windows-x64-$variant-Setup"
    $files = @(
        Get-ChildItem -LiteralPath $releaseDir -File |
            Where-Object { $_.Name -eq "$baseName.exe" -or $_.Name -like "$baseName-*.bin" } |
            Sort-Object Name
    )
    if (-not $files) { continue }
    $entries = foreach ($file in $files) {
        [ordered]@{
            name = $file.Name
            url = "$base/$($file.Name)"
            size = $file.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
            installer = $file.Extension -eq ".exe"
        }
    }
    $variants[$variant] = [ordered]@{
        label = if ($variant -eq "CPU") { "CPU" } else { "GPU NVIDIA CUDA 12.4" }
        files = @($entries)
    }
}
if (-not $variants.Count) {
    throw "Installer CPU/GPU belum ditemukan di $releaseDir"
}
$manifest = [ordered]@{
    version = "0.2.0"
    release_url = "https://github.com/Marshel2727/vision-entok/releases/tag/v0.2.0"
    variants = $variants
}
$manifestPath = Join-Path $releaseDir "websetup-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
"$hash  websetup-manifest.json" | Set-Content -LiteralPath ($manifestPath + ".sha256") -Encoding ascii
Write-Host "READY $manifestPath"
