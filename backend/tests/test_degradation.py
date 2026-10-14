"""TC-04 ~ TC-07：状态机抑制（冷却/去重）与异常降级（过期/冲突/超时/恢复）。"""
from datetime import timedelta

import pytest

from app.schemas.rule_ast import UnifiedMonitorRule
from app.services import chaos_injector, data_adapter as da, state_machine


def _price_rule(thr=300.0):
    """构造一条在离线回退数据下必然触发的简单规则（宁德 mock 价 288.35 < 300）。"""
    return UnifiedMonitorRule.model_validate({
        "rule_name": "测试·价格监控",
        "original_nl_query": "宁德时代跌破 300 元提醒我",
        "ai_interpretation_summary": "测试规则",
        "rule_tree": {
            "group_id": "root", "logical_op": "AND",
            "conditions": [{
                "condition_id": "cond_1", "label": "宁德时代最新价跌破 300 元",
                "category": "PRICE_VALUATION", "target_code": "300750.SZ", "target_name": "宁德时代",
                "metric_field": "last_price", "operator": "<", "threshold_value": thr,
                "unit": "元", "statistical_caliber": "扶摇行情快照",
                "primary_source": "FUYAO_QUOTE", "backup_source": None, "staleness_tolerance_seconds": 900}],
            "sub_groups": []},
        "schedule_config": {"interval_seconds": 60, "cooldown_minutes": 60, "dedup_window_minutes": 240},
    })


def _new_task(db):
    from app.models import MonitorTask, TaskRuleVersion

    rule = _price_rule()
    t = MonitorTask(title=rule.rule_name, status=MonitorTask.ACTIVE,
                    current_version=1, current_rule_json=rule.model_dump())
    db.add(t)
    db.flush()
    db.add(TaskRuleVersion(task_id=t.id, version_num=1, rule_json=rule.model_dump(), change_type="NL_INIT"))
    db.commit()
    return t


@pytest.mark.asyncio
async def test_tc04_cooldown_and_dedup(db):
    """触发 -> 冷却拦截 -> 清冷却 -> 同指纹去重拦截。"""
    t = _new_task(db)
    log1 = await state_machine.run_evaluation(db, t, respect_schedule=False)
    assert log1.outcome_type == "DEGRADED_API_FALLBACK"  # 无密钥环境：命中依赖离线回退数据，不正式触发

    # 用 monkeypatch 语义：直接给一个健康的 OK 结果验证触发链（模拟有密钥环境）
    ok = da.DataFetchResult(
        status=da.STATUS_OK,
        data={"item": [{"last_price": 288.35}]},
        data_timestamp=da.now_bj(), source_name="扶摇金融数据API",
        endpoint_or_tool="GET /api/a-share/prices/snapshot")
    orig = da.get_stock_quote
    da.get_stock_quote = _ret(ok)
    try:
        log1 = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log1.outcome_type == "TRIGGERED_ALERT"
        assert t.status == "COOLDOWN" and t.cooldown_until is not None

        log2 = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log2.outcome_type == "SUPPRESSED_BY_COOLDOWN"
        assert log2.cooldown_remaining_seconds > 3500

        t.cooldown_until = None
        db.commit()
        log3 = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log3.outcome_type == "SUPPRESSED_BY_DEDUP"
        assert log3.dedup_fingerprint == log1.dedup_fingerprint
    finally:
        da.get_stock_quote = orig


@pytest.mark.asyncio
async def test_tc05_stale_data(db):
    """数据过期（+45min）-> DEGRADED_STALE_DATA，不正式触发。"""
    t = _new_task(db)
    stale = da.DataFetchResult(
        status=da.STATUS_STALE,
        data={"item": [{"last_price": 288.35}]},
        data_timestamp=da.now_bj() - timedelta(minutes=45),
        source_name="扶摇金融数据API", endpoint_or_tool="GET /api/a-share/prices/snapshot")
    orig = da.get_stock_quote
    da.get_stock_quote = _ret(stale)
    try:
        log = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log.outcome_type == "DEGRADED_STALE_DATA"
        assert t.status == "DEGRADED"
        cit = log.condition_details_json[0]["citation"]
        assert cit["is_stale"] is True
        assert cit["staleness_seconds"] > 900
    finally:
        da.get_stock_quote = orig


@pytest.mark.asyncio
async def test_tc06_source_conflict(db):
    """双源价格冲突 -> DEGRADED_CONFLICT_HOLD，挂起判定并列展示。"""
    t = _new_task(db)
    conflict = da.DataFetchResult(
        status=da.STATUS_CONFLICT,
        data={"item": [{"last_price": 288.35}]},
        data_timestamp=da.now_bj(), source_name="扶摇金融数据API",
        endpoint_or_tool="GET /api/a-share/prices/snapshot",
        conflict_with={"source": "iFinD 快照", "value": 292.26, "diff_pct": 1.36})
    orig = da.get_stock_quote
    da.get_stock_quote = _ret(conflict)
    try:
        log = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log.outcome_type == "DEGRADED_CONFLICT_HOLD"
        d = log.condition_details_json[0]
        assert d["is_met"] is None
        assert d["citation"]["conflict_with"]["diff_pct"] == 1.36
    finally:
        da.get_stock_quote = orig


@pytest.mark.asyncio
async def test_tc07_api_timeout_and_recovery(client, db):
    """接口超时 -> 降级（缓存/离线回退口径，不得静默'正常'）-> 恢复。"""
    t = _new_task(db)
    chaos_injector.set_fault("API_TIMEOUT")
    try:
        log = await state_machine.run_evaluation(db, t, respect_schedule=False)
        assert log.outcome_type == "DEGRADED_API_FALLBACK"
        assert log.degradation_flag is True
        # 不允许静默正常结论
        assert log.outcome_type != "NOT_TRIGGERED_NORMAL"

        # 恢复：注入健康 OK 数据源（模拟上游接口恢复实时响应）
        chaos_injector.set_fault("NORMAL")
        t.status = "DEGRADED"
        db.commit()
        ok = da.DataFetchResult(
            status=da.STATUS_OK, data={"item": [{"last_price": 288.35}]},
            data_timestamp=da.now_bj(), source_name="扶摇金融数据API",
            endpoint_or_tool="GET /api/a-share/prices/snapshot")
        orig = da.get_stock_quote
        da.get_stock_quote = _ret(ok)
        try:
            log2 = await state_machine.run_evaluation(db, t, respect_schedule=False)
        finally:
            da.get_stock_quote = orig
        assert log2.outcome_type == "TRIGGERED_ALERT"
        assert "[RECOVERY]" in log2.explanation_json["inference_list"][0]
        assert log2.task_state_after in ("ACTIVE", "COOLDOWN")
    finally:
        chaos_injector.set_fault("NORMAL")


def _ret(res):
    async def f(*a, **k):
        return res
    return f
