#!/usr/bin/env bash
# AlphaRadar 一键安装并启动（仅需 Python 3.10+，无需 Node/Docker）
# 用法：bash start.sh   然后浏览器打开 http://localhost:8000
# 可选环境变量：
#   PIP_INDEX_URL  覆盖默认的清华 PyPI 镜像（海外网络可设为 https://pypi.org/simple）
#   PORT           覆盖默认端口 8000
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "错误：未找到 python3，请先安装 Python 3.10+"; exit 1
fi

# 默认使用清华镜像加速（国内网络直连 PyPI 很慢）；如已配置全局镜像则沿用
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# 虚拟环境（已存在则复用）
if [ ! -d backend/.venv ]; then
  echo "[1/3] 创建虚拟环境 backend/.venv ..."
  "$PYTHON" -m venv backend/.venv
fi

echo "[2/3] 安装依赖（镜像：$PIP_INDEX，首次约 1 分钟）..."
backend/.venv/bin/pip install -q -i "$PIP_INDEX" -r backend/requirements.txt

PORT="${PORT:-8000}"
echo "[3/3] 启动 AlphaRadar → http://localhost:$PORT  （Ctrl+C 停止）"
exec backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --app-dir backend
