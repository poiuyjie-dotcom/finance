"""系统设置路由：数据源密钥配置、连通性测试、调度参数。"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from .. import config
from ..services import data_adapter as da

router = APIRouter()

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# 可在 .env 持久化的键（密钥类做掩码展示）
_SECRET_KEYS = ["FUYAO_API_KEY", "IFIND_API_KEY", "JEV_API_KEY", "LLM_API_KEY"]
_PLAIN_KEYS = ["LLM_BASE_URL", "LLM_MODEL", "FUYAO_API_BASE", "IFIND_MCP_BASE", "JEV_MODEL",
               "SCHEDULER_TICK_SECONDS", "ENABLE_HIGH_FIDELITY_FALLBACK"]


def _mask(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 12:
        return v[:4] + "*" * (len(v) - 4)
    return f"{v[:10]}…{v[-4:]}（{len(v)} 字符）"


def _settings_view() -> dict:
    keys = {}
    for k in _SECRET_KEYS:
        v = os.environ.get(k, "")
        keys[k] = {"configured": bool(v), "masked": _mask(v)}
    for k in _PLAIN_KEYS:
        keys[k] = {"configured": bool(os.environ.get(k, "")), "masked": os.environ.get(k, "")}
    return {
        "keys": keys,
        "env_file": str(_ENV_PATH),
        "env_writable": os.access(_ENV_PATH.parent, os.W_OK),
        "scheduler_tick_seconds": config.SCHEDULER_TICK_SECONDS,
        "tz": config.TZ_NAME,
        "health": {"fuyao": da.get_health()["FUYAO"], "ifind": da.get_health()["IFIND"]},
    }


@router.get("/settings")
def get_settings():
    return _settings_view()


class KeysUpdate(BaseModel):
    FUYAO_API_KEY: str | None = None
    IFIND_API_KEY: str | None = None
    JEV_API_KEY: str | None = None
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str | None = None
    SCHEDULER_TICK_SECONDS: int | None = None


def _persist_env(updates: dict[str, str]) -> None:
    """把变更写回 backend/.env（不覆盖未提及的行）。"""
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text("utf-8").splitlines()
    seen = set()
    out = []
    for line in lines:
        m = re.match(r"^([A-Z_]+)\s*=", line)
        if m and m.group(1) in updates:
            out.append(f"{m.group(1)}={updates[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    _ENV_PATH.write_text("\n".join(out) + "\n", "utf-8")


@router.post("/settings/keys")
def update_keys(req: KeysUpdate):
    applied = []
    data = req.model_dump(exclude_none=True)
    updates: dict[str, str] = {}
    for k, v in data.items():
        if k == "SCHEDULER_TICK_SECONDS":
            v = str(max(10, int(v)))
        if not str(v).strip() and k in _SECRET_KEYS:
            continue  # 空值不覆盖已有密钥
        os.environ[k] = str(v)
        updates[k] = str(v)
        applied.append(k)
    # 运行时立即生效
    for k, v in updates.items():
        setattr(config, k, v if not k.endswith("TICK_SECONDS") else int(v))
    # iFinD 会话与新密钥绑定，切换后重置
    da._ifind_sessions.clear()
    if updates:
        _persist_env(updates)
    # 调度周期热更新
    if "SCHEDULER_TICK_SECONDS" in updates:
        try:
            from ..services import scheduler_engine
            if scheduler_engine.scheduler.running:
                scheduler_engine.scheduler.remove_job("global_tick")
                scheduler_engine.scheduler.add_job(
                    scheduler_engine.tick, "interval", seconds=config.SCHEDULER_TICK_SECONDS,
                    id="global_tick", max_instances=1, coalesce=True)
        except Exception:  # noqa: BLE001
            pass  # 调度器未运行（如测试环境）时忽略
    return {"applied": applied, "note": "已写入 .env 并即时生效（iFinD 会话已重置）", **_settings_view()}


@router.post("/settings/test")
async def test_connections():
    """逐源连通性测试：返回 ok / 延迟 / 错误详情。"""
    import asyncio

    async def test_fuyao():
        t0 = time.time()
        try:
            headers = {"X-api-key": config.FUYAO_API_KEY} if config.FUYAO_API_KEY else {}
            async with httpx.AsyncClient(timeout=10) as ac:
                r = await ac.get(f"{config.FUYAO_API_BASE}/api/a-share/prices/snapshot?thscodes=600519.SH",
                                 headers=headers)
                body = r.json()
            ok = body.get("code") == 0
            return {"ok": ok, "latency_ms": int((time.time() - t0) * 1000),
                    "detail": "行情快照正常" if ok else f"code={body.get('code')} {body.get('message')}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "latency_ms": int((time.time() - t0) * 1000), "detail": f"{type(e).__name__}: {e}"}

    async def test_ifind():
        t0 = time.time()
        r = await da.ifind_call("stock", "get_stock_summary", {"query": "贵州茅台 最新价"})
        lat = int((time.time() - t0) * 1000)
        if r.status == da.STATUS_OK:
            return {"ok": True, "latency_ms": lat, "detail": "tools/call 正常"}
        return {"ok": False, "latency_ms": lat, "detail": r.error_detail[:120]}

    async def test_jev():
        t0 = time.time()
        if not config.JEV_API_KEY:
            return {"ok": False, "latency_ms": 0, "detail": "未配置 JEV_API_KEY"}
        from ..services import jev_client
        r = await jev_client.jev_evaluate("connectivity test", {
            "ok": {"type": "noul", "instructions": "Is this a connectivity test?"}})
        lat = int((time.time() - t0) * 1000)
        return {"ok": r is not None, "latency_ms": lat,
                "detail": "systemone 正常" if r else jev_client.get_status()["last_error"][:120]}

    fuyao, ifind, jev = await asyncio.gather(test_fuyao(), test_ifind(), test_jev())
    return {"fuyao": fuyao, "ifind": ifind, "jev": jev}
