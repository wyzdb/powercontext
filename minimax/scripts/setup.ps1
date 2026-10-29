# 一键初始化 MiniMax 环境（Windows PowerShell）
# 用法: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Write-Host "[1/3] 创建虚拟环境 .venv"
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv
    }

    Write-Host "[2/3] 安装依赖"
    & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

    Write-Host "[3/3] 准备配置"
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "已生成 .env，请填写 MINIMAX_API_KEY 后运行：" -ForegroundColor Yellow
        Write-Host "  .\.venv\Scripts\python.exe tools\check_minimax.py" -ForegroundColor Yellow
    } else {
        Write-Host ".env 已存在，保持不变"
    }
}
finally {
    Pop-Location
}
