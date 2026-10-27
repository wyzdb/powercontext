param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepo
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
$target = Join-Path $TargetRepo "minimax"

if (-not (Test-Path $TargetRepo)) {
    Write-Error "target repository does not exist: $TargetRepo"
    exit 1
}
if (-not (Test-Path (Join-Path $TargetRepo ".git"))) {
    Write-Warning "no .git found under $TargetRepo; continuing with a plain copy"
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
robocopy $source $target /E /XD .env .state __pycache__ .pytest_cache .tmp /XF .env /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy failed with exit code $LASTEXITCODE"
    exit 1
}

$problems = @()
if (Test-Path (Join-Path $target ".env")) { $problems += ".env was copied" }
if (Test-Path (Join-Path $target ".state")) { $problems += ".state was copied" }
$service = Join-Path $target "business\src\orderflow\service.py"
if (-not (Test-Path $service)) {
    $problems += "business sources are missing"
} elseif (Select-String -Path $service -Pattern "created_after" -SimpleMatch -Quiet) {
    $problems += "business code is not in the pre-change state (created_after present)"
}

Write-Host "copied $source -> $target"
if ($problems.Count -gt 0) {
    $problems | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "checks passed: no .env, no .state, business code in pre-change state"
Write-Host "next:"
Write-Host "  cd `"$TargetRepo`""
Write-Host "  git checkout 2026-competition-ecosystem"
Write-Host "  git add minimax"
Write-Host "  git commit -m `"feat(minimax): SDD context management system`""
Write-Host "  git push origin 2026-competition-ecosystem"
Write-Host "  git rev-parse HEAD"
