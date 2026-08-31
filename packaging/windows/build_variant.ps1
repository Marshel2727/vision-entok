param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("CPU", "GPU-CUDA124")]
    [string]$Variant,
    [string]$PythonExecutable = $env:ENTOK_BUILD_PYTHON,
    [ValidateSet("Production", "All")]
    [string]$ModelSet = "Production",
    [string]$SignToolPath = $env:ENTOK_SIGNTOOL,
    [string]$CodeSigningThumbprint = $env:ENTOK_SIGNING_THUMBPRINT,
    [switch]$SkipDependencyInstall,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$buildRoot = Join-Path $projectRoot "artifacts\build\windows"
$releaseRoot = Join-Path $projectRoot "artifacts\release\0.2.0"
$venvName = if ($Variant -eq "CPU") { ".venv-cpu" } else { ".venv-gpu-cu124" }
$venvPath = Join-Path $buildRoot $venvName
$pythonPath = Join-Path $venvPath "Scripts\python.exe"
$requirements = if ($Variant -eq "CPU") { "cpu.txt" } else { "gpu-cu124.txt" }

New-Item -ItemType Directory -Force -Path $buildRoot, $releaseRoot | Out-Null
if (($SignToolPath -and -not $CodeSigningThumbprint) -or ($CodeSigningThumbprint -and -not $SignToolPath)) {
    throw "Code signing memerlukan SignToolPath dan CodeSigningThumbprint sekaligus."
}

function Invoke-EntokCodeSign([string]$FilePath) {
    if (-not $SignToolPath) {
        return
    }
    & $SignToolPath sign /sha1 $CodeSigningThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "Code signing gagal: $FilePath"
    }
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (-not $PythonExecutable) {
        $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
        $PythonExecutable = Get-ChildItem -LiteralPath $localPythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'Python3(12|13)' } |
            Sort-Object FullName |
            Select-Object -Last 1 -ExpandProperty FullName
    }
    if (-not $PythonExecutable -or -not (Test-Path -LiteralPath $PythonExecutable)) {
        throw "Python 3.12 atau 3.13 x64 tidak ditemukan. Atur ENTOK_BUILD_PYTHON ke python.exe yang valid."
    }
    & $PythonExecutable -m venv $venvPath
}

if (-not $SkipDependencyInstall) {
    & $pythonPath -m pip install --upgrade pip
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot "requirements\$requirements")
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot "requirements\build.txt")
}

& $pythonPath (Join-Path $PSScriptRoot "generate_icon.py")

$variantDist = Join-Path $buildRoot ("output-" + $Variant)
$variantWork = Join-Path $buildRoot ("pyinstaller-" + $Variant)
if (Test-Path -LiteralPath $variantDist) {
    Remove-Item -LiteralPath $variantDist -Recurse -Force
}
if (Test-Path -LiteralPath $variantWork) {
    Remove-Item -LiteralPath $variantWork -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $variantDist, $variantWork | Out-Null

$env:YOLO_AUTOINSTALL = "false"
$env:YOLO_CONFIG_DIR = Join-Path $variantWork "ultralytics-config"
$env:ENTOK_MODEL_SET = $ModelSet.ToLowerInvariant()
& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $variantDist `
    --workpath $variantWork `
    (Join-Path $PSScriptRoot "entok_vision_lite.spec")

$appDir = Join-Path $variantDist "EntokVisionLite"
if (-not (Test-Path -LiteralPath (Join-Path $appDir "EntokVisionLite.exe"))) {
    throw "PyInstaller tidak menghasilkan EntokVisionLite.exe untuk $Variant"
}
Invoke-EntokCodeSign (Join-Path $appDir "EntokVisionLite.exe")

$portableDir = Join-Path $variantDist "portable"
if (Test-Path -LiteralPath $portableDir) {
    Remove-Item -LiteralPath $portableDir -Recurse -Force
}
Copy-Item -LiteralPath $appDir -Destination $portableDir -Recurse
New-Item -ItemType File -Force -Path (Join-Path $portableDir "portable.flag") | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README-PORTABLE.txt") -Destination $portableDir

$zipName = "EntokVisionLite-0.2.0-Windows-x64-$Variant-Portable.zip"
$zipPath = Join-Path $releaseRoot $zipName
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $portableDir "*") -DestinationPath $zipPath -CompressionLevel Optimal

if (-not $SkipInstaller) {
    $isccCandidates = @(
        @(
            (Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
            "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    )
    if (-not $isccCandidates) {
        throw "Inno Setup ISCC.exe belum tersedia. Pasang Inno Setup atau gunakan -SkipInstaller."
    }
    $installerDir = $releaseRoot
    New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
    $iconPath = Join-Path $PSScriptRoot "assets\entok_vision_lite.ico"
    & $isccCandidates[0] `
        "/DVariant=$Variant" `
        "/DSourceDir=$appDir" `
        "/DOutputDir=$installerDir" `
        "/DIconFile=$iconPath" `
        (Join-Path $PSScriptRoot "installer\entok_vision_lite.iss")
}

$artifacts = @($zipPath)
$installerBaseName = "EntokVisionLite-0.2.0-Windows-x64-$Variant-Setup"
$installerFiles = @(
    Get-ChildItem -LiteralPath $releaseRoot -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq ($installerBaseName + ".exe") -or
            $_.Name -like ($installerBaseName + "-*.bin")
        } |
        Sort-Object Name
)
if ($installerFiles) {
    foreach ($installerFile in $installerFiles) {
        if ($installerFile.Extension -eq ".exe") {
            Invoke-EntokCodeSign $installerFile.FullName
        }
    }
    $artifacts += $installerFiles.FullName
}
foreach ($artifact in $artifacts) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
    "$hash  $([IO.Path]::GetFileName($artifact))" | Set-Content -LiteralPath ($artifact + ".sha256") -Encoding ascii
    Write-Host "READY $artifact"
}
