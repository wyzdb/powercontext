#!/bin/sh
# 温故容器启动：等 seekdb 就绪 → 建表 → 导语料 → 起服务
set -e

HOST="${SEEKDB_HOST:-seekdb}"
PORT="${SEEKDB_PORT:-2881}"

echo "[wengu] 等待 seekdb ${HOST}:${PORT} ..."
i=1
while [ "$i" -le 60 ]; do
  if python -c "import os,socket;s=socket.socket();s.settimeout(2);s.connect(('${HOST}',int('${PORT}')))" 2>/dev/null; then
    echo "[wengu] seekdb 已就绪"
    break
  fi
  i=$((i+1))
  sleep 3
done

echo "[wengu] 初始化数据库..."
python scripts/init_db.py || echo "[wengu] init_db 跳过（可能已初始化）"

echo "[wengu] 导入语料..."
python -m app.ingest || echo "[wengu] ingest 跳过"

echo "[wengu] 启动服务 :8000"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
