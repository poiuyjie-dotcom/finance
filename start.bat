@echo off
REM AlphaRadar 一键安装并启动（Windows，仅需 Python 3.10+）
REM 默认使用清华镜像；海外网络可先执行：set PIP_INDEX_URL=https://pypi.org/simple
cd /d "%~dp0"
if "%PIP_INDEX_URL%"=="" set PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
if not exist backend\.venv (
  echo [1/3] 创建虚拟环境 ...
  python -m venv backend\.venv
)
echo [2/3] 安装依赖 ...
backend\.venv\Scripts\pip install -q -i %PIP_INDEX_URL% -r backend\requirements.txt
echo [3/3] 启动 AlphaRadar -^> http://localhost:8000
backend\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
