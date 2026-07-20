<#
.SYNOPSIS
Builds a Windows x64, no-Python-runtime distribution of ELP Stereo Camera App.

.DESCRIPTION
Runs PyInstaller from the project virtual environment and packages the onedir
output as build/release/ELPStereoCamera-v<version>-win64.zip. Existing release
archives are deliberately never overwritten.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$spec = Join-Path $projectRoot "build\windows\ELPStereoCamera.spec"
$distPath = Join-Path $projectRoot "build\dist"
$workPath = Join-Path $projectRoot "build\work"
$releaseRoot = Join-Path $projectRoot "build\release"
$buildLog = Join-Path $workPath "pyinstaller.log"
$buildErrorLog = Join-Path $workPath "pyinstaller-error.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment is missing. Run: uv sync --group dev"
}

Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Force -Path $workPath | Out-Null
    $version = (& $python -c "from elp_console import __version__; print(__version__)").Trim()
    if (-not ($version -match '^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$')) {
        throw "Invalid application version '$version'."
    }

    # Start-Process avoids PowerShell treating PyInstaller's normal progress
    # output on stderr as a terminating error. It still waits synchronously
    # and preserves stdout/stderr in build/work for diagnosis.
    $arguments = @(
        "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", $distPath,
        "--workpath", $workPath,
        $spec
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments -Wait -PassThru `
        -WindowStyle Hidden -RedirectStandardOutput $buildLog -RedirectStandardError $buildErrorLog
    if ($process.ExitCode -ne 0) {
        Get-Content -LiteralPath $buildErrorLog -Tail 80
        throw "PyInstaller failed with exit code $($process.ExitCode)."
    }

    $bundle = Join-Path $distPath "ELPStereoCamera"
    if (-not (Test-Path -LiteralPath (Join-Path $bundle "ELPStereoCamera.exe"))) {
        throw "PyInstaller completed without ELPStereoCamera.exe."
    }

    New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
    $archive = Join-Path $releaseRoot "ELPStereoCamera-v$version-win64.zip"
    if (Test-Path -LiteralPath $archive) {
        throw "Refusing to overwrite an existing release archive: $archive"
    }

    Compress-Archive -LiteralPath $bundle -DestinationPath $archive
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $hasLauncher = $null -ne ($zip.Entries | Where-Object {
            $_.FullName -match '^ELPStereoCamera[/\\]ELPStereoCamera\.exe$'
        } | Select-Object -First 1)
    }
    finally {
        $zip.Dispose()
    }
    if (-not $hasLauncher) {
        throw "Release archive is missing ELPStereoCamera/ELPStereoCamera.exe."
    }
    Write-Host "Created $archive (PyInstaller log: $buildLog)"
}
finally {
    Pop-Location
}
