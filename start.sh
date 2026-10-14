#!/usr/bin/env bash
# AlphaRadar 一键安装并启动（仅需 Python 3.10+，无需 Node/Docker）
# 用法：bash start.sh   然后浏览器打开 http://localhost:8000
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "错误：未找到 python3，请先安装 Python 3.10+"; exit 1
fi

# 虚拟环境（已存在则复用）
if [ ! -d backend/.venv ]; then
  echo "[1/3] 创建虚拟环境 backend/.venv ..."
  "$PYTHON" -m venv backend/.venv
fi

echo "[2/3] 安装依赖（首次约 1 分钟）..."
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "[3/3] 启动 AlphaRadar → http://localhost:8000  （Ctrl+C 停止）"
exec backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
