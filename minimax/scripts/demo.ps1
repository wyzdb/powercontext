# 一键演示：导入资料 → 生成上下文 → 验收 → 跑测试
# 用法: powershell -ExecutionPolicy Bypass -File scripts/demo.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "找不到 $python，请先按 README 第 3 节初始化虚拟环境"
}

function Step($title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

Step "1/4 导入规格 / 代码 / 测试到 seekdb"
& $python -m ctx.cli import

Step "2/4 生成任务上下文"
& $python -m ctx.cli build --task "为任务列表增加按标签筛选" --task-id TASK-001 --out records\context-TASK-001.json | Out-Null
Write-Host "已写入 records\context-TASK-001.json"

Step "3/4 验收：上下文是否包含规定的规格、代码、测试"
& $python scripts\verify_context.py
if ($LASTEXITCODE -ne 0) { throw "上下文验收失败" }

Step "4/4 样例工程测试（改前应为 7 failed / 8 passed）"
& $python scripts\run_tests.py --label demo
Write-Host ""
Write-Host "完成。测试红灯是预期的：补丁尚未生成。" -ForegroundColor Yellow
