param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
if (-not (Test-Path $envPath)) {
    Write-Error "environment file not found: $envPath (copy .env.example to .env first)"
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "python is not on PATH"
    exit 1
}

Write-Host "starting PowerContext Server with $envPath"
& $python.Source (Join-Path $root "scripts\powercontext_server.py") $envPath
