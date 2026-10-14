"""环境变量配置。所有密钥只从环境变量读取，绝不硬编码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

FUYAO_API_BASE = os.getenv("FUYAO_API_BASE", "https://fuyao.aicubes.cn")
FUYAO_API_KEY = os.getenv("FUYAO_API_KEY", "")

IFIND_MCP_BASE = os.getenv("IFIND_MCP_BASE", "https://api-mcp.51ifind.com:8643/ds-mcp-servers")
IFIND_API_KEY = os.getenv("IFIND_API_KEY", "")

# LLM 可选：未配置时自然语言编译走内置确定性解析器
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'radar.db'}")

# 无密钥时启用本地高仿真回退数据，保证演示与测试可用
ENABLE_HIGH_FIDELITY_FALLBACK = os.getenv("ENABLE_HIGH_FIDELITY_FALLBACK", "true").lower() == "true"

TZ_NAME = "Asia/Shanghai"

# 调度器全局巡检周期（秒）
SCHEDULER_TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "30"))

# 多源交叉验证冲突阈值：同一标的双源 last_price 偏差百分比
CROSS_SOURCE_CONFLICT_PCT = 0.5
