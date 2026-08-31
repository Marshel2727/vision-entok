param(
    [string]$SignToolPath = $env:ENTOK_SIGNTOOL,
    [string]$CodeSigningThumbprint = $env:ENTOK_SIGNING_THUMBPRINT
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$outputDir = Join-Path $projectRoot "artifacts\release\0.2.0"
$outputPath = Join-Path $outputDir "EntokVisionLite-0.2.0-WebSetup.exe"
$frameworkRoot = Join-Path $env:WINDIR "Microsoft.NET\Framework64"
$compiler = Get-ChildItem -LiteralPath $frameworkRoot -Filter csc.exe -Recurse |
    Sort-Object FullName |
    Select-Object -Last 1 -ExpandProperty FullName
if (-not $compiler) {
    throw "Compiler C# Windows tidak ditemukan. Aktifkan .NET Framework 4.x."
}
if (($SignToolPath -and -not $CodeSigningThumbprint) -or ($CodeSigningThumbprint -and -not $SignToolPath)) {
    throw "Code signing memerlukan SignToolPath dan CodeSigningThumbprint sekaligus."
}
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
& $compiler /nologo /target:winexe /optimize+ `
    /reference:System.dll `
    /reference:System.Drawing.dll `
    /reference:System.Windows.Forms.dll `
    /reference:System.Web.Extensions.dll `
    /out:$outputPath `
    (Join-Path $PSScriptRoot "websetup\WebSetupConfig.cs") `
    (Join-Path $PSScriptRoot "websetup\Program.cs")
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputPath)) {
    throw "Build WebSetup gagal."
}
if ($SignToolPath) {
    & $SignToolPath sign /sha1 $CodeSigningThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $outputPath
    if ($LASTEXITCODE -ne 0) { throw "Code signing WebSetup gagal." }
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outputPath).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($outputPath))" | Set-Content -LiteralPath ($outputPath + ".sha256") -Encoding ascii
Write-Host "READY $outputPath"
