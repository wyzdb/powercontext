#!/usr/bin/env bash
# 一键初始化 MiniMax 环境（macOS / Linux）
# 用法: bash scripts/setup.sh

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "[1/3] 创建虚拟环境 .venv"
[ -x ".venv/bin/python" ] || python3 -m venv .venv

echo "[2/3] 安装依赖"
./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] 准备配置"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "已生成 .env，请填写 MINIMAX_API_KEY 后运行："
  echo "  ./.venv/bin/python tools/check_minimax.py"
else
  echo ".env 已存在，保持不变"
fi
