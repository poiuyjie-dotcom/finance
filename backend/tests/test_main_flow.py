"""TC-01 ~ TC-03：主链路（NL 转规则 → 评估归因 → 版本 Diff 与回滚）。"""
import pytest

from app.schemas.rule_ast import UnifiedMonitorRule


def test_tc01_nl_to_rule_ast(client):
    """自然语言解析为复合规则树（价格+换手率+公告），结构与口径正确。"""
    r = client.post("/api/v1/tasks/parse-nl", json={
        "nl_query": "当宁德时代跌破 200 元且换手率大于 3%，或者出现减持公告时提醒我"})
    assert r.status_code == 200
    body = r.json()
    assert body["compliance_passed"] is True
    rule = UnifiedMonitorRule.model_validate(body["draft_rule"])

    root = rule.rule_tree
    assert root.logical_op.value == "OR"
    # 顶层公告条件 + AND 子组（价格 + 换手率）
    labels = [c.label for c in root.conditions]
    assert any("公告" in l for l in labels)
    assert len(root.sub_groups) == 1
    sub = root.sub_groups[0]
    assert sub.logical_op.value == "AND"
    assert len(sub.conditions) == 2
    price = [c for c in sub.conditions if c.metric_field == "last_price"][0]
    assert price.target_code == "300750.SZ"
    assert float(price.threshold_value) == 200.0
    assert price.unit == "元"
    assert price.statistical_caliber  # 口径非空
    assert price.primary_source is not None


def test_tc02_evaluate_with_why_not_attribution(client, db):
    """评估 + 逐条件归因：实测值/阈值/证据溯源字段完整。"""
    tasks = client.get("/api/v1/tasks").json()
    assert len(tasks) >= 3  # 预置任务
    tid = [t for t in tasks if "宁德" in t["title"]][0]["id"]

    r = client.post(f"/api/v1/tasks/{tid}/evaluate-now")
    assert r.status_code == 200
    log = r.json()
    assert log["outcome_type"] in {
        "TRIGGERED_ALERT", "NOT_TRIGGERED_NORMAL", "DEGRADED_API_FALLBACK",
        "SUPPRESSED_BY_COOLDOWN", "SUPPRESSED_BY_DEDUP"}
    assert log["condition_details"], "必须有逐条件明细"
    for d in log["condition_details"]:
        c = d["citation"]
        assert c["source_name"] and c["endpoint_or_tool"]
        assert c["data_timestamp"] and c["fetch_timestamp"]
        assert c["unit"] and c["statistical_caliber"]
        assert d["reason_snippet"]
    # 三段式解释
    exp = log["explanation"]
    assert exp["facts_list"] and exp["inference_list"] and exp["uncertainty_and_degradation_note"]


def test_tc03_rule_version_diff_and_rollback(client, db):
    """修改阈值 -> v2 + 字段级 Diff -> 回滚 v1。"""
    from sqlalchemy import select

    from app.models import MonitorTask
    from app.services import state_machine

    task = db.execute(select(MonitorTask).where(MonitorTask.title.like("%宁德%"))).scalar_one()
    rule = UnifiedMonitorRule.model_validate(task.current_rule_json)

    # 修改价格阈值 290 -> 295
    for g_cond in rule.rule_tree.sub_groups[0].conditions:
        if g_cond.metric_field == "last_price":
            g_cond.threshold_value = 295.0
    version = state_machine.update_rule_version(db, task, rule, "MANUAL_EDIT", "测试：上调阈值")
    assert task.current_version == 2
    changes = version.diff_summary["changes"]
    assert any("threshold_value" in c["path"] and "290" in c["old_value"] and "295" in c["new_value"]
               for c in changes)
    # 版本钩子重置冷却与去重
    assert task.cooldown_until is None and task.last_dedup_hash is None

    # 回滚到 v1
    r = client.post(f"/api/v1/tasks/{task.id}/rollback/1")
    assert r.status_code == 200
    db.refresh(task)
    assert task.current_version == 3
    restored = UnifiedMonitorRule.model_validate(task.current_rule_json)
    thr = [c.threshold_value for g in restored.rule_tree.sub_groups for c in g.conditions
           if c.metric_field == "last_price"][0]
    assert float(thr) == 290.0
