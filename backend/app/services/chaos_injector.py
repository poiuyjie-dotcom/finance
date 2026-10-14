"""异常故障注入模拟器：一键制造 数据过期 / 双源冲突 / 接口超时，用于演示与测试降级链路。"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()

# mode: NORMAL / STALE_DATA / SOURCE_CONFLICT / API_TIMEOUT
_state: dict = {
    "mode": "NORMAL",
    "target_code": "",
    "activated_at": "",
}


def set_fault(mode: str, target_code: str = "") -> dict:
    with _LOCK:
        _state["mode"] = mode
        _state["target_code"] = target_code
        _state["activated_at"] = _now_iso() if mode != "NORMAL" else ""
    return get_state()


def get_state() -> dict:
    with _LOCK:
        return dict(_state)


def get_mode() -> str:
    return get_state()["mode"]


def _now_iso() -> str:
    from datetime import datetime, timezone, timedelta

    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat(timespec="seconds")
