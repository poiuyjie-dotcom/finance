"""统一数据接入层：扶摇 REST + iFinD MCP，含交叉验证、三级降级与故障注入联动。

降级策略（对齐设计方案 §4.3）：
1. 数据过期：data_timestamp 滞后超容忍阈值 -> 状态 DEGRADED_STALE_DATA
2. 多源冲突：双源 last_price 偏差 > 0.5% -> DEGRADED_CONFLICT_HOLD（不静默任选其一）
3. 接口失败：2 次退避重试 -> 本地缓存回退（CACHE_FALLBACK）/ 高仿真回退数据（MOCK_FALLBACK）
"""
from __future__ import annotations

import asyncio
import json
import re
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .. import config
from . import chaos_injector

TZ = timezone(timedelta(hours=8))

MOCK = json.loads((Path(__file__).resolve().parent.parent / "mock_data" / "a_share_snapshots.json").read_text("utf-8"))


# ---------------------------------------------------------------- 工具函数
def now_bj() -> datetime:
    return datetime.now(TZ)


def iso_bj(dt: datetime | None = None) -> str:
    return (dt or now_bj()).isoformat(timespec="seconds")


def ms_to_bj(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, TZ)


# ---------------------------------------------------------------- 结果包装器
STATUS_OK = "OK"
STATUS_STALE = "STALE"
STATUS_CONFLICT = "CONFLICT"
STATUS_CACHE_FALLBACK = "CACHE_FALLBACK"
STATUS_MOCK_FALLBACK = "MOCK_FALLBACK"
STATUS_FAILED = "FAILED"


@dataclass
class DataFetchResult:
    status: str
    data: Any = None
    data_timestamp: datetime | None = None
    fetch_timestamp: datetime = field(default_factory=now_bj)
    source_name: str = ""
    endpoint_or_tool: str = ""
    error_detail: str = ""
    conflict_with: dict | None = None
    degraded: bool = False

    def staleness_seconds(self, tolerance: int) -> int:
        if not self.data_timestamp:
            return 0
        return max(0, int((self.fetch_timestamp - self.data_timestamp).total_seconds()))

    def is_stale(self, tolerance: int) -> bool:
        if self.status == STATUS_FAILED:
            return False
        return self.staleness_seconds(tolerance) > tolerance


# ---------------------------------------------------------------- 本地缓存与数据源健康度
_cache: dict[str, DataFetchResult] = {}
_health: dict[str, dict] = {
    "FUYAO": {"status": "UNKNOWN", "last_sync": "", "last_error": ""},
    "IFIND": {"status": "UNKNOWN", "last_sync": "", "last_error": ""},
}


def get_health() -> dict:
    return {k: dict(v) for k, v in _health.items()}


async def _mark_health(source: str, ok: bool, error: str = "") -> None:
    # 健康度写入为原子字典操作，不使用跨事件循环的 asyncio.Lock（测试环境 loop 轮换）
    _health[source]["status"] = "HEALTHY" if ok else "ERROR"
    _health[source]["last_sync"] = iso_bj()
    _health[source]["last_error"] = error


# ---------------------------------------------------------------- 交易日历（带缓存）
_calendar_cache: dict = {"days": set(), "fetched_at": None}


def _weekday_trading_days_approx() -> set[str]:
    """交易日历接口失败时的近似（周一至周五），调用方必须标注不确定性。"""
    days = set()
    d = now_bj().date() - timedelta(days=30)
    for _ in range(60):
        if d.weekday() < 5:
            days.add(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return days


def market_phase(now: datetime | None = None) -> dict:
    """返回当前 A 股市场阶段：NON_TRADING_DAY / PRE_OPEN / CONTINUOUS_AUCTION / LUNCH_BREAK / AFTER_CLOSE"""
    now = now or now_bj()
    days = _calendar_cache["days"] or _weekday_trading_days_approx()
    today = now.strftime("%Y%m%d")
    is_trading_day = today in days
    hm = now.hour * 100 + now.minute
    if not is_trading_day:
        phase = "NON_TRADING_DAY"
    elif hm < 915:
        phase = "PRE_OPEN"
    elif 915 <= hm < 930:
        phase = "CALL_AUCTION"
    elif 930 <= hm < 1130:
        phase = "CONTINUOUS_AUCTION"
    elif 1130 <= hm < 1300:
        phase = "LUNCH_BREAK"
    elif 1300 <= hm < 1457:
        phase = "CONTINUOUS_AUCTION"
    else:
        phase = "AFTER_CLOSE"
    return {"is_trading_day": is_trading_day, "phase": phase}


async def refresh_calendar() -> None:
    """拉取扶摇交易日历并缓存 12 小时；跨零点后（当日不在缓存集合）立即刷新；
    失败时退化为工作日近似。"""
    today = now_bj().strftime("%Y%m%d")
    if (_calendar_cache["fetched_at"]
            and (now_bj() - _calendar_cache["fetched_at"]) < timedelta(hours=12)
            and today in _calendar_cache["days"]):
        return
    r = await _fuyao_get("/api/a-share/calendar/trading-days", source="FUYAO_CALENDAR", use_cache=False)
    days = set()
    if r.status in (STATUS_OK, STATUS_CACHE_FALLBACK):
        items = (r.data or {}).get("item") or []
        days = {str(x.get("date")) for x in items if x.get("date")}
    if not days:
        days = _weekday_trading_days_approx()
    _calendar_cache["days"] = days
    _calendar_cache["fetched_at"] = now_bj()


# ---------------------------------------------------------------- 扶摇 REST
_client: httpx.AsyncClient | None = None
_client_loop = None


def _http() -> httpx.AsyncClient:
    """按当前事件循环惰性创建/重建客户端（测试环境中 loop 会轮换）。

    旧 loop 上的客户端不做 aclose——其传输绑定在已关闭的循环上，关闭操作本身会抛错；
    直接弃用引用交由 GC 回收即可。
    """
    global _client, _client_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _client is None or _client.is_closed or loop is not _client_loop:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        _client_loop = loop
    return _client


async def _fuyao_get(path: str, source: str = "FUYAO", use_cache: bool = True) -> DataFetchResult:
    """扶摇 REST GET，含故障注入、重试、缓存与高仿真回退。"""
    mode = chaos_injector.get_mode()

    # 故障注入：接口超时
    if mode == "API_TIMEOUT":
        await _mark_health("FUYAO", False, "模拟上游接口超时（故障注入）")
        return await _fallback_chain(path, "模拟扶摇接口超时（故障注入 API_TIMEOUT）", use_cache)

    headers = {"X-api-key": config.FUYAO_API_KEY} if config.FUYAO_API_KEY else {}
    last_err = ""
    for attempt, backoff in enumerate([0, 1, 3]):
        if backoff:
            await asyncio.sleep(backoff)
        try:
            resp = await _http().get(f"{config.FUYAO_API_BASE}{path}", headers=headers)
            body = resp.json()
            if body.get("code") != 0:
                raise RuntimeError(f"业务错误 code={body.get('code')} message={body.get('message')}")
            await _mark_health("FUYAO", True)
            data_ts = ms_to_bj(body["data"]["timestamp"]) if body.get("data", {}).get("timestamp") else now_bj()
            return DataFetchResult(
                status=STATUS_OK,
                data=body["data"],
                data_timestamp=data_ts,
                source_name="扶摇金融数据API",
                endpoint_or_tool=f"GET {path}",
            )
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
    await _mark_health("FUYAO", False, last_err)
    return await _fallback_chain(path, last_err, use_cache)


async def _fallback_chain(path: str, err: str, use_cache: bool) -> DataFetchResult:
    """缓存 -> 高仿真回退数据。绝不返回'看起来正常'的空数据。"""
    if use_cache and path in _cache:
        c = _cache[path]
        return DataFetchResult(
            status=STATUS_CACHE_FALLBACK,
            data=c.data,
            data_timestamp=c.data_timestamp,
            source_name=c.source_name + "（本地缓存回退）",
            endpoint_or_tool=c.endpoint_or_tool,
            error_detail=f"上游失败后回退本地缓存；原始错误：{err}",
            degraded=True,
        )
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        return DataFetchResult(
            status=STATUS_MOCK_FALLBACK,
            data=None,
            data_timestamp=now_bj(),
            source_name="本地高仿真回退数据（离线演示，非实时）",
            endpoint_or_tool=f"mock{path}",
            error_detail=f"上游失败且回退离线数据；原始错误：{err}",
            degraded=True,
        )
    return DataFetchResult(status=STATUS_FAILED, error_detail=err, source_name="扶摇金融数据API", endpoint_or_tool=path, degraded=True)


# ---------------------------------------------------------------- iFinD MCP
_ifind_sessions: dict[str, str] = {}
_ifind_ids: dict[str, int] = {}
# 免费版限流 2 请求/秒：全局串行 + 最小间隔，避免连续巡检触发限流
# 锁需跟随当前事件循环重建（测试环境 loop 轮换，跨 loop 的 asyncio.Lock 会失效）
_ifind_lock: asyncio.Lock | None = None
_ifind_lock_loop = None
_ifind_last_call = 0.0
_IFIND_MIN_INTERVAL = 0.55


def _get_ifind_lock() -> asyncio.Lock:
    global _ifind_lock, _ifind_lock_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _ifind_lock is None or loop is not _ifind_lock_loop:
        _ifind_lock = asyncio.Lock()
        _ifind_lock_loop = loop
    return _ifind_lock

_SERVERS = {
    "stock": "/hexin-ifind-ds-stock-mcp",
    "fund": "/hexin-ifind-ds-fund-mcp",
    "edb": "/hexin-ifind-ds-edb-mcp",
    "news": "/hexin-ifind-ds-news-mcp",
    "bond": "/hexin-ifind-ds-bond-mcp",
    "global_stock": "/hexin-ifind-ds-global-stock-mcp",
    "index": "/hexin-ifind-ds-index-mcp",
    "future": "/hexin-ifind-ds-futures-mcp",
}


async def ifind_call(server: str, tool: str, arguments: dict) -> DataFetchResult:
    """调用 iFinD MCP Tool（JSON-RPC over HTTP，Authorization 裸 token）。全局节流防限流。"""
    if not config.IFIND_API_KEY:
        return DataFetchResult(
            status=STATUS_FAILED,
            error_detail="未配置 IFIND_API_KEY",
            source_name="iFinD MCP",
            endpoint_or_tool=f"{server}/{tool}",
            degraded=True,
        )
    if chaos_injector.get_mode() == "API_TIMEOUT":
        await _mark_health("IFIND", False, "模拟 iFinD MCP 超时（故障注入）")
        return DataFetchResult(
            status=STATUS_FAILED,
            error_detail="模拟 iFinD MCP 调用超时（故障注入 API_TIMEOUT）",
            source_name="iFinD MCP",
            endpoint_or_tool=f"{server}/{tool}",
            degraded=True,
        )

    global _ifind_last_call
    async with _get_ifind_lock():
        wait = _IFIND_MIN_INTERVAL - (asyncio.get_event_loop().time() - _ifind_last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _ifind_last_call = asyncio.get_event_loop().time()
        try:
            return await _ifind_call_inner(server, tool, arguments)
        except Exception as e:  # noqa: BLE001
            _ifind_sessions.pop(server, None)
            await _mark_health("IFIND", False, f"{type(e).__name__}: {e}")
            return DataFetchResult(
                status=STATUS_FAILED,
                error_detail=f"{type(e).__name__}: {e}",
                source_name="iFinD MCP",
                endpoint_or_tool=f"{server}/{tool}",
                degraded=True,
            )


async def _ifind_call_inner(server: str, tool: str, arguments: dict) -> DataFetchResult:
    base = config.IFIND_MCP_BASE + _SERVERS[server]
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": config.IFIND_API_KEY,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as ac:
        # initialize（无会话时）
        if server not in _ifind_sessions:
            _ifind_ids[server] = _ifind_ids.get(server, 0) + 1
            r = await ac.post(base, headers=headers, json={
                "jsonrpc": "2.0", "id": _ifind_ids[server], "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "alpharadar", "version": "1.0.0"}},
            })
            r.raise_for_status()
            sid = r.headers.get("mcp-session-id")
            if not sid:
                raise RuntimeError("initialize 成功但未返回 Mcp-Session-Id")
            _ifind_sessions[server] = sid
            await ac.post(base, headers={**headers, "Mcp-Session-Id": sid},
                          json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        sid = _ifind_sessions[server]
        _ifind_ids[server] = _ifind_ids.get(server, 0) + 1
        r = await ac.post(base, headers={**headers, "Mcp-Session-Id": sid}, json={
            "jsonrpc": "2.0", "id": _ifind_ids[server], "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        })
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"MCP error: {body['error']}")
        await _mark_health("IFIND", True)
        return DataFetchResult(
            status=STATUS_OK,
            data=body,
            data_timestamp=now_bj(),
            source_name="iFinD MCP",
            endpoint_or_tool=f"{server}/{tool}",
        )


# ---------------------------------------------------------------- 面向评估器的原子取数
async def get_stock_quote(thscode: str) -> DataFetchResult:
    """股票行情快照（扶摇主源；SOURCE_CONFLICT 注入时构造 iFinD 冲突值）。"""
    path = f"/api/a-share/prices/snapshot?thscodes={thscode}"
    r = await _fuyao_get(path)
    mode = chaos_injector.get_mode()
    if mode == "STALE_DATA" and r.status == STATUS_OK:
        r.data_timestamp = r.data_timestamp - timedelta(minutes=45)
        r.status = STATUS_STALE
        r.degraded = True
    if r.status == STATUS_OK:
        items = (r.data or {}).get("item") or []
        if not items:
            return DataFetchResult(status=STATUS_FAILED, error_detail=f"扶摇未返回 {thscode} 行情（item 为空）",
                                   source_name="扶摇金融数据API", endpoint_or_tool=f"GET {path}", degraded=True)
        _cache[path] = r
        if mode == "SOURCE_CONFLICT":
            primary = float(items[0].get("last_price") or 0)
            conflict_value = round(primary * 1.0136, 2)  # +1.36% 偏差
            r.conflict_with = {
                "source": "iFinD 快照（模拟冲突注入）",
                "value": conflict_value,
                "data_timestamp": iso_bj(r.data_timestamp),
                "diff_pct": round(abs(conflict_value - primary) / primary * 100, 2) if primary else None,
            }
            r.status = STATUS_CONFLICT
            r.degraded = True
    elif r.status == STATUS_MOCK_FALLBACK:
        q = MOCK["quotes"].get(thscode)
        if not q:
            return DataFetchResult(status=STATUS_FAILED, error_detail=f"离线数据中无 {thscode}",
                                   source_name="本地高仿真回退数据", endpoint_or_tool=f"mock{path}", degraded=True)
        r.data = {"item": [dict(q, thscode=thscode)], "timestamp": int(now_bj().timestamp() * 1000)}
    return r


async def get_index_quote(thscode: str) -> DataFetchResult:
    path = f"/api/a-share-index/prices/snapshot?thscodes={thscode}"
    r = await _fuyao_get(path)
    if r.status == STATUS_OK:
        _cache[path] = r
    elif r.status == STATUS_MOCK_FALLBACK:
        q = MOCK["index_quotes"].get(thscode)
        if q:
            r.data = {"item": [dict(q, thscode=thscode)], "timestamp": int(now_bj().timestamp() * 1000)}
        else:
            r.status = STATUS_FAILED
            r.error_detail = f"离线数据中无指数 {thscode}"
    return r


async def get_valuation(thscode: str) -> DataFetchResult:
    path = f"/api/a-share/valuations/snapshot?thscodes={thscode}"
    r = await _fuyao_get(path)
    if r.status == STATUS_OK:
        _cache[path] = r
    elif r.status == STATUS_MOCK_FALLBACK:
        v = MOCK["valuations"].get(thscode)
        if v:
            r.data = {"item": [dict(v, thscode=thscode)], "timestamp": int(now_bj().timestamp() * 1000)}
        else:
            r.status = STATUS_FAILED
            r.error_detail = f"离线数据中无 {thscode} 估值"
    return r


async def get_hot_list() -> DataFetchResult:
    path = "/api/a-share/special-data/hot-stock-list"
    r = await _fuyao_get(path)
    if r.status == STATUS_OK:
        _cache[path] = r
    elif r.status == STATUS_MOCK_FALLBACK:
        r.data = {"item": MOCK["hot_list"], "timestamp": int(now_bj().timestamp() * 1000)}
    return r


async def get_hot_rank(thscode: str) -> DataFetchResult:
    """个股热榜排名（从热榜快照推导）。未上榜是确定事实（排名在榜单之外），不算数据异常。"""
    r = await get_hot_list()
    if r.status in (STATUS_OK, STATUS_MOCK_FALLBACK):
        item_count = len((r.data or {}).get("item") or [])
        for it in (r.data or {}).get("item") or []:
            if it.get("thscode") == thscode:
                return DataFetchResult(status=r.status, data={"rank": it.get("rank"), "name": it.get("name")},
                                       data_timestamp=r.data_timestamp, source_name=r.source_name,
                                       endpoint_or_tool=r.endpoint_or_tool, degraded=r.degraded,
                                       error_detail=r.error_detail)
        return DataFetchResult(status=r.status, data={"rank": None, "name": None,
                                                      "note": f"未进入热榜榜单（榜单共 {item_count} 名）"},
                               data_timestamp=r.data_timestamp, source_name=r.source_name,
                               endpoint_or_tool=r.endpoint_or_tool, degraded=r.degraded,
                               error_detail=r.error_detail)
    return r


async def get_turnover_rate(thscode: str, name: str = "") -> DataFetchResult:
    """换手率：扶摇股票快照无此字段，路由到 iFinD get_stock_summary（按表格列定位取数）。"""
    r = await ifind_call("stock", "get_stock_summary", {"query": f"{name or thscode} 最新换手率"})
    if r.status == STATUS_OK:
        text = _extract_ifind_text(r.data)
        val = _to_float(_table_value(text, "换手率", thscode))
        if val is None:
            val = _parse_first_number_after(text, "换手率")
        if val is None:
            return DataFetchResult(status=STATUS_FAILED, error_detail=f"iFinD 返回中未解析到换手率：{text[:150]}",
                                   source_name="iFinD MCP", endpoint_or_tool="stock/get_stock_summary", degraded=True)
        return DataFetchResult(status=STATUS_OK, data={"turnover_rate_pct": val, "raw_text": text[:300]},
                               data_timestamp=now_bj(), source_name="iFinD MCP",
                               endpoint_or_tool="stock/get_stock_summary")
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        q = MOCK["quotes"].get(thscode)
        if q and "turnover_rate_pct" in q:
            return DataFetchResult(status=STATUS_MOCK_FALLBACK,
                                   data={"turnover_rate_pct": q["turnover_rate_pct"]},
                                   data_timestamp=now_bj(),
                                   source_name="本地高仿真回退数据（离线演示，非实时）",
                                   endpoint_or_tool="mock:turnover_rate", degraded=True,
                                   error_detail=r.error_detail)
    return r


async def get_index_pe(thscode: str, name: str = "") -> DataFetchResult:
    """指数 PE：扶摇估值接口不支持指数（实测 code=3001），路由到 iFinD index_data。"""
    r = await ifind_call("index", "index_data", {"query": f"{name or thscode} 最新市盈率PE"})
    if r.status == STATUS_OK:
        text = _extract_ifind_text(r.data)
        # 指数代码存在 000300.SH/399300.SZ 双写法，查询已限定标的，直接取首行
        val = _to_float(_table_value(text, "市盈率", None))
        if val is None:
            val = _parse_first_number_after(text, "市盈率")
        if val is None:
            return DataFetchResult(status=STATUS_FAILED, error_detail=f"iFinD 返回中未解析到指数PE：{text[:150]}",
                                   source_name="iFinD MCP", endpoint_or_tool="index/index_data", degraded=True)
        return DataFetchResult(status=STATUS_OK, data={"pe_ttm": val, "raw_text": text[:300]},
                               data_timestamp=now_bj(), source_name="iFinD MCP", endpoint_or_tool="index/index_data")
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        v = MOCK["index_valuations"].get(thscode)
        if v:
            return DataFetchResult(status=STATUS_MOCK_FALLBACK, data=dict(v), data_timestamp=now_bj(),
                                   source_name="本地高仿真回退数据（离线演示，非实时）",
                                   endpoint_or_tool="mock:index_pe", degraded=True, error_detail=r.error_detail)
    return r


async def search_announcements(thscode: str, name: str, keywords: list[str]) -> DataFetchResult:
    """公告关键词检索（iFinD search_notice，近 7 天窗口）。命中返回 hit_titles。"""
    kw = "/".join(keywords[:3]) if keywords else "公告"
    end = now_bj().strftime("%Y-%m-%d")
    start = (now_bj() - timedelta(days=7)).strftime("%Y-%m-%d")
    r = await ifind_call("news", "search_notice",
                         {"query": f"{name} {kw}", "time_start": start, "time_end": end, "size": 10})
    if r.status == STATUS_OK:
        text = _extract_ifind_text(r.data)
        hits = [ln for ln in text.splitlines() if any(k in ln for k in keywords)] if keywords else []
        return DataFetchResult(status=STATUS_OK,
                               data={"hit_titles": hits[:5], "raw_text": text[:400], "keyword_matched": bool(hits)},
                               data_timestamp=now_bj(), source_name="iFinD MCP", endpoint_or_tool="news/search_notice")
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        anns = MOCK["announcements"].get(thscode, [])
        hits = [a["title"] for a in anns if any(k in (a.get("title") or "") for k in keywords)] if keywords else []
        return DataFetchResult(status=STATUS_MOCK_FALLBACK,
                               data={"hit_titles": hits[:5], "raw_text": json.dumps(anns, ensure_ascii=False)[:400],
                                     "keyword_matched": bool(hits)},
                               data_timestamp=now_bj(),
                               source_name="本地高仿真回退数据（离线演示，非实时）",
                               endpoint_or_tool="mock:announcements", degraded=True, error_detail=r.error_detail)
    return r


async def get_days_to_earnings(thscode: str, name: str = "") -> DataFetchResult:
    """距离下一财报披露日的交易日数（iFinD get_stock_events，按报告期措辞取数）。"""
    season = _next_report_season()
    r = await ifind_call("stock", "get_stock_events", {"query": f"{name or thscode} {season} 预计披露日期"})
    if r.status == STATUS_OK:
        text = _extract_ifind_text(r.data)
        cell = _table_value(text, "预计披露", thscode) or _table_value(text, "披露", thscode)
        date_val = _parse_first_date(cell) if cell else _parse_first_date(text)
        if date_val and date_val >= now_bj().strftime("%Y%m%d"):
            days = _trading_days_between(now_bj().strftime("%Y%m%d"), date_val)
            return DataFetchResult(status=STATUS_OK, data={"days_to_earnings": days, "target_date": date_val,
                                                           "raw_text": text[:200]},
                                   data_timestamp=now_bj(), source_name="iFinD MCP",
                                   endpoint_or_tool="stock/get_stock_events")
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        d = MOCK["calendar"]["next_earnings_dates"].get(thscode)
        if d:
            days = _trading_days_between(now_bj().strftime("%Y%m%d"), d)
            return DataFetchResult(status=STATUS_MOCK_FALLBACK, data={"days_to_earnings": days, "target_date": d},
                                   data_timestamp=now_bj(), source_name="本地高仿真回退数据（离线演示，非实时）",
                                   endpoint_or_tool="mock:earnings_calendar", degraded=True, error_detail=r.error_detail)
    return DataFetchResult(status=STATUS_FAILED, error_detail=r.error_detail or "财报日历数据不可用",
                           source_name="iFinD MCP", endpoint_or_tool="stock/get_stock_events", degraded=True)


def _next_report_season() -> str:
    """按当前月份推算下一个应披露的定期报告期（用于 iFinD 查询措辞）。"""
    m = now_bj().month
    if m in (1, 2, 3, 4):
        return "年报"
    if m in (4, 5, 6):
        return "一季报"
    if m in (7, 8):
        return "半年报"
    return "三季报"


async def get_futures_pct_chg(variety_name: str) -> DataFetchResult:
    """商品期货主力涨跌幅（iFinD future_quotes）。"""
    r = await ifind_call("future", "future_quotes", {"query": f"{variety_name}主力合约最新涨跌幅"})
    if r.status == STATUS_OK:
        text = _extract_ifind_text(r.data)
        val = _parse_pct_after(text, "涨跌幅")
        if val is None:
            val = _parse_first_signed_pct(text)
        if val is None:
            return DataFetchResult(status=STATUS_FAILED, error_detail=f"iFinD 返回中未解析到期货涨跌幅：{text[:120]}",
                                   source_name="iFinD MCP", endpoint_or_tool="future/future_quotes", degraded=True)
        return DataFetchResult(status=STATUS_OK, data={"pct_chg": val, "raw_text": text[:300]},
                               data_timestamp=now_bj(), source_name="iFinD MCP", endpoint_or_tool="future/future_quotes")
    if config.ENABLE_HIGH_FIDELITY_FALLBACK:
        f = MOCK["futures"].get(variety_name)
        if f:
            return DataFetchResult(status=STATUS_MOCK_FALLBACK, data=dict(f), data_timestamp=now_bj(),
                                   source_name="本地高仿真回退数据（离线演示，非实时）",
                                   endpoint_or_tool="mock:futures", degraded=True, error_detail=r.error_detail)
    return r


# ---------------------------------------------------------------- 解析辅助
def _extract_ifind_text(body: Any) -> str:
    try:
        content = body["result"]["content"]
        parts = []
        for c in content:
            t = c.get("text", "")
            inner = json.loads(t)
            d = inner.get("data")
            if isinstance(d, str):
                parts.append(d)
            elif isinstance(d, dict):
                # dict 型返回（如 index_data）取其中的字符串字段（answer 等），保留真实换行
                for v in d.values():
                    if isinstance(v, str) and v.strip():
                        parts.append(v)
            elif d is not None:
                parts.append(json.dumps(d, ensure_ascii=False))
        return "\n".join(parts)
    except Exception:  # noqa: BLE001
        return json.dumps(body, ensure_ascii=False)[:500]


def _parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """解析 markdown 表格：返回 (表头列, 数据行)。"""
    lines = [l for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    header = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    rows = []
    for l in lines[1:]:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if cells and all(set(c) <= set("-—: \t") for c in cells):
            continue
        rows.append(cells)
    return header, rows


def _table_value(text: str, col_kw: str, row_kw: str | None = None) -> str | None:
    """按列名关键词定位单元格；row_kw 匹配行首标的。取第一个非空值。"""
    header, rows = _parse_table(text)
    if not header:
        return None
    for idx, h in enumerate(header):
        if col_kw in h:
            for row in rows:
                if row_kw and not any(row_kw in c for c in row[:2]):
                    continue
                if idx < len(row) and row[idx] and row[idx] not in ("\\t", "-"):
                    return row[idx]
    return None


def _to_float(s: str | None) -> float | None:
    if not s:
        return None
    import re

    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def _parse_first_number_after(text: str, anchor: str) -> float | None:
    idx = text.find(anchor)
    if idx < 0:
        return None
    import re

    m = re.search(r"-?\d+(\.\d+)?", text[idx + len(anchor): idx + len(anchor) + 60])
    return float(m.group()) if m else None


def _parse_pct_after(text: str, anchor: str) -> float | None:
    return _parse_first_number_after(text, anchor)


def _parse_first_signed_pct(text: str) -> float | None:
    import re

    m = re.search(r"[-+]\d+(\.\d+)?%", text)
    return float(m.group().rstrip("%")) if m else None


_DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})"),
    re.compile(r"\b(20\d{2})(\d{2})(\d{2})\b"),  # 紧凑 20261021
]


def _parse_first_date(text: str) -> str | None:
    best: tuple[int, str] | None = None
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            y, mo, d = m.groups()
            if mo == "00" or d == "00":
                continue
            try:
                datetime(int(y), int(mo), int(d))
            except ValueError:
                continue
            key = f"{int(y):04d}{int(mo):02d}{int(d):02d}"
            if best is None or m.start() < best[0]:
                best = (m.start(), key)
    return best[1] if best else None


def _trading_days_between(start: str, end: str) -> int:
    """未来日期超出日历覆盖（扶摇日历仅回溯近一年）时，按工作日近似。"""
    days = _calendar_cache["days"]
    cal_max = max(days) if days else None
    try:
        s = datetime.strptime(start, "%Y%m%d").date()
        e = datetime.strptime(end, "%Y%m%d").date()
    except ValueError:
        return -1
    n, cur = 0, s
    while cur < e:
        cur += timedelta(days=1)
        key = cur.strftime("%Y%m%d")
        if days and key <= (cal_max or ""):
            if key in days:
                n += 1
        elif cur.weekday() < 5:
            n += 1
    return n
