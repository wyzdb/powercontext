#!/usr/bin/env bash
# 温故 · 一键初始化脚本
# 用法：bash scripts/init_demo.sh
# 前置：Docker 已启动（docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb:latest）

set -e

cd "$(dirname "$0")/.."

echo "=== 温故 · 初始化 ==="
echo ""

# 1. 检查 seekdb 连接
echo "[1/4] 检查 seekdb 连接..."
python scripts/smoke_test.py || {
  echo ""
  echo "seekdb 未启动。请先运行："
  echo "  docker run -d --name seekdb -p 2881:2881 -p 2886:2886 oceanbase/seekdb:latest"
  exit 1
}

# 2. 安装 Python 依赖
echo ""
echo "[2/5] 安装 Python 依赖..."
pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 初始化数据库
echo ""
echo "[3/5] 初始化数据库（建库建表）..."
python scripts/init_db.py

# 4. 入库
echo ""
echo "[4/5] 导入语料（6 篇 / 23 节）..."
python -m app.ingest

# 5. 启动服务
echo ""
echo "[5/5] 启动服务..."
echo ""
echo "=== 初始化完成 ==="
echo "浏览器打开：http://127.0.0.1:8080"
echo ""
echo "四个接口："
echo "  POST /api/ask        带出处的混合检索"
echo "  GET  /api/quiz       按概念出题"
echo "  POST /api/grade      判分 + 写回弱点"
echo "  GET  /api/profile/{learner}  弱点画像"
echo ""

python -m uvicorn app.main:app --port 8080 --host 0.0.0.0
