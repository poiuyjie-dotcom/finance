"""数据源路由：健康度、市场阶段、行情预览。"""
from fastapi import APIRouter

from ..services import chaos_injector, data_adapter as da

router = APIRouter()


@router.get("/health")
async def health():
    await da.refresh_calendar()
    phase = da.market_phase()
    return {
        "status": "OK",
        "fuyao": da.get_health()["FUYAO"],
        "ifind": da.get_health()["IFIND"],
        "chaos": chaos_injector.get_state(),
        "trading_calendar": {"is_trading_day": phase["is_trading_day"], "market_phase": phase["phase"],
                             "now_bj": da.iso_bj()},
    }


@router.get("/preview-quote")
async def preview_quote(code: str = "300750.SZ"):
    """标的行情预览（供前端标的选择器展示实测值）。"""
    r = await da.get_stock_quote(code)
    item = ((r.data or {}).get("item") or [{}])[0]
    return {
        "status": r.status, "source": r.source_name, "endpoint": r.endpoint_or_tool,
        "data_timestamp": da.iso_bj(r.data_timestamp), "fetch_timestamp": da.iso_bj(r.fetch_timestamp),
        "staleness_seconds": r.staleness_seconds(900), "conflict_with": r.conflict_with,
        "quote": {"thscode": code, "last_price": item.get("last_price"),
                  "pct_chg": item.get("price_change_ratio_pct")},
        "error_detail": r.error_detail,
    }
