"""确定性规则评估器：所有数值比较由 Python 计算，逐叶子条件记录实测值、阈值与证据。

AI 绝不参与数值判定——这是本产品的核心合规设计。
"""
from __future__ import annotations

from typing import Any

from ..schemas.log_schema import ConditionEvaluationDetail, EvidenceCitation, StructuredExplanation
from ..schemas.rule_ast import (
    ComparisonOperator,
    ConditionCategory,
    ConditionLeaf,
    DataSourceType,
    RuleGroup,
)
from . import data_adapter as da
from .compliance_guard import sanitize_text

KNOWN_INDEX_CODES = {"000300.SH", "000001.SH", "000905.SH", "000852.SH", "399001.SZ", "399006.SZ", "399303.SZ"}

OP_SYMBOL = {
    ComparisonOperator.GT: ">",
    ComparisonOperator.GTE: ">=",
    ComparisonOperator.LT: "<",
    ComparisonOperator.LTE: "<=",
    ComparisonOperator.EQ: "==",
}


def _is_index(cond: ConditionLeaf) -> bool:
    return cond.target_code.endswith(".TI") or cond.target_code in KNOWN_INDEX_CODES


class EvaluationResult:
    def __init__(self) -> None:
        self.condition_details: list[ConditionEvaluationDetail] = []
        self.overall: bool | None = None
        self.has_stale = False
        self.has_conflict = False
        self.has_failure = False
        self.has_mock = False
        self.has_cache_fallback = False
        self.notes: list[str] = []


def _citation(res: da.DataFetchResult, field_name: str, raw_value: Any, unit: str, caliber: str, tolerance: int) -> EvidenceCitation:
    return EvidenceCitation(
        source_name=res.source_name,
        endpoint_or_tool=res.endpoint_or_tool,
        raw_field_name=field_name,
        raw_value=raw_value,
        unit=unit,
        statistical_caliber=caliber,
        data_timestamp=da.iso_bj(res.data_timestamp),
        fetch_timestamp=da.iso_bj(res.fetch_timestamp),
        is_stale=res.is_stale(tolerance),
        staleness_seconds=res.staleness_seconds(tolerance),
        conflict_with=res.conflict_with,
    )


def _fmt(v: Any, unit: str) -> str:
    if isinstance(v, float):
        return f"{v:.4g} {unit}".strip()
    return f"{v} {unit}".strip()


async def evaluate_condition(cond: ConditionLeaf, resolution: dict | None = None) -> ConditionEvaluationDetail:
    """评估单个叶子条件，绑定原始字段证据。

    resolution: 用户对双源冲突的人工裁决（TRUST_PRIMARY/TRUST_BACKUP/MANUAL），
    存在时冲突条件按裁决值判定并在证据中标注 resolved_by，而非挂起。
    """
    tol = cond.staleness_tolerance_seconds
    metric = cond.metric_field
    op = cond.operator
    thr = cond.threshold_value

    # ---------- 事件类：公告关键词 ----------
    if cond.category == ConditionCategory.EVENT_ANNOUNCEMENT or metric == "announcement_keywords":
        res = await da.search_announcements(cond.target_code, cond.target_name,
                                            thr if isinstance(thr, list) else [str(thr)])
        matched = bool((res.data or {}).get("keyword_matched")) if res.status != da.STATUS_FAILED else None
        if res.status == da.STATUS_FAILED:
            is_met = None
            reason = f"公告数据获取失败，无法判定：{res.error_detail}"
        else:
            hits = (res.data or {}).get("hit_titles") or []
            matched = bool(hits)
            is_met = matched if op in (ComparisonOperator.CONTAINS_ANY, ComparisonOperator.EQ) else (not matched)
            if matched:
                reason = f"近24小时公告检索命中关键词：{'; '.join(hits[:2])}"
            else:
                reason = "近24小时公告检索未命中任何关键词"
        cit = _citation(res, "hit_titles", (res.data or {}).get("hit_titles") if res.data else None,
                        "篇", "近24小时公告标题与正文关键词匹配", tol)
        # Jev 情绪归因（可选）：仅增强解释，不改变 is_met 的确定性判定
        if matched:
            from . import jev_client
            if jev_client.is_enabled():
                sem = await jev_client.announcement_sentiment(
                    (res.data or {}).get("hit_titles") or [],
                    thr if isinstance(thr, list) else [str(thr)])
                if sem:
                    reason += (f"｜Jev 语义归因：{sem['sentiment']}"
                               f"（置信度 {sem['sentiment_confidence']:.2f}，重大利空概率 {sem['material_negative_p']:.2f}）")
                    cit.raw_value = {"hit_titles": (res.data or {}).get("hit_titles"),
                                     "jev_sentiment": sem}
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=("命中" if matched else "未命中") if matched is not None else "数据异常",
            threshold_display=f"包含 {thr if isinstance(thr, list) else [thr]} 之一",
            reason_snippet=reason, citation=cit)

    # ---------- 日历类：距离财报披露日 ----------
    if metric == "days_to_earnings":
        res = await da.get_days_to_earnings(cond.target_code, cond.target_name)
        if res.status == da.STATUS_FAILED:
            cit = _citation(res, "days_to_earnings", None, "个交易日", "下一定期报告披露日推算", tol)
            return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                             actual_value_display="数据异常", threshold_display=f"{op.value} {thr} 个交易日",
                                             reason_snippet=f"财报日历获取失败：{res.error_detail}", citation=cit)
        days = res.data["days_to_earnings"]
        if op == ComparisonOperator.OUTSIDE_WINDOW:
            is_met = days > float(thr)
        else:
            is_met = days <= float(thr)
        cit = _citation(res, "days_to_earnings", days, "个交易日",
                        f"目标披露日 {res.data.get('target_date', '未知')}，按交易日推算", tol)
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=_fmt(days, "个交易日"), threshold_display=f"{'>' if op == ComparisonOperator.OUTSIDE_WINDOW else '<='} {thr} 个交易日",
            reason_snippet=f"距离下次财报披露约 {days} 个交易日（目标日 {res.data.get('target_date')}），阈值 {thr}",
            citation=cit)

    # ---------- 热度类：热榜排名 ----------
    if metric == "hot_rank":
        res = await da.get_hot_rank(cond.target_code)
        if res.status == da.STATUS_FAILED:
            cit = _citation(res, "rank", None, "名", "扶摇热榜快照（盘中约每5分钟刷新）", tol)
            return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                             actual_value_display="数据异常",
                                             threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 名",
                                             reason_snippet=f"热榜数据不可判定：{res.error_detail}", citation=cit)
        rank = res.data.get("rank")
        if rank is None:
            is_met = _numeric_compare(999999, op, float(thr))  # 未上榜 => 排名视为超出榜单范围
            cit = _citation(res, "rank", None, "名", "扶摇热榜快照（盘中约每5分钟刷新）", tol)
            return ConditionEvaluationDetail(
                condition_id=cond.condition_id, label=cond.label, is_met=is_met,
                actual_value_display="未上榜",
                threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 名",
                reason_snippet=f"{cond.target_name} 当前未进入热榜榜单（{res.data.get('note', '')}），条件{'满足' if is_met else '不满足'}",
                citation=cit)
        is_met = _numeric_compare(rank, op, float(thr))
        cit = _citation(res, "rank", rank, "名", "扶摇热榜快照（盘中约每5分钟刷新）", tol)
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=_fmt(rank, "名"), threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 名",
            reason_snippet=f"当前热榜排名 {rank} 名，阈值 {OP_SYMBOL.get(op, op.value)} {thr} 名，条件{'满足' if is_met else '不满足'}",
            citation=cit)

    # ---------- 期货涨跌幅 ----------
    if metric == "futures_pct_chg":
        res = await da.get_futures_pct_chg(cond.target_name)
        if res.status == da.STATUS_FAILED:
            cit = _citation(res, "pct_chg", None, "%", "iFinD 期货主力合约日频涨跌幅", tol)
            return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                             actual_value_display="数据异常",
                                             threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} %",
                                             reason_snippet=f"期货行情获取失败：{res.error_detail}", citation=cit)
        pct = res.data["pct_chg"]
        is_met = _numeric_compare(pct, op, float(thr))
        cit = _citation(res, "pct_chg", pct, "%", "iFinD 期货主力合约日频涨跌幅", tol)
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=_fmt(pct, "%"), threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} %",
            reason_snippet=f"{cond.target_name}主力涨跌幅实测 {pct}%，阈值 {OP_SYMBOL.get(op, op.value)} {thr}%，条件{'满足' if is_met else '不满足'}",
            citation=cit)

    # ---------- 换手率（iFinD） ----------
    if metric in ("turnover_rate_pct", "turnover_rate"):
        res = await da.get_turnover_rate(cond.target_code, cond.target_name)
        if res.status == da.STATUS_FAILED:
            cit = _citation(res, "turnover_rate_pct", None, "%", "iFinD 个股日频换手率（自然语言取数）", tol)
            return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                             actual_value_display="数据异常",
                                             threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} %",
                                             reason_snippet=f"换手率获取失败：{res.error_detail}", citation=cit)
        val = res.data["turnover_rate_pct"]
        is_met = _numeric_compare(val, op, float(thr))
        cit = _citation(res, "turnover_rate_pct", val, "%", "iFinD 个股日频换手率（自然语言取数）", tol)
        gap = _gap_pct(val, op, float(thr))
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=_fmt(val, "%"), threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} %",
            reason_snippet=f"换手率实测 {val}%，阈值 {OP_SYMBOL.get(op, op.value)} {thr}%，条件{'满足' if is_met else '不满足'}",
            citation=cit, gap_pct=gap)

    # ---------- 估值类 ----------
    if metric in ("pe_ttm", "pe_mrq", "pb_mrq"):
        if _is_index(cond):
            res = await da.get_index_pe(cond.target_code, cond.target_name)
            field = "pe_ttm"
            caliber = "iFinD 指数市盈率（TTM，报表公告日基准）"
            if res.status == da.STATUS_FAILED or res.data is None or res.data.get("pe_ttm") is None:
                cit = _citation(res, field, None, "倍", caliber, tol)
                return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                                 actual_value_display="数据异常",
                                                 threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 倍",
                                                 reason_snippet=f"估值数据获取失败：{res.error_detail}", citation=cit)
            val = float(res.data["pe_ttm"])
        else:
            res = await da.get_valuation(cond.target_code)
            field = metric
            caliber = "扶摇估值快照（TTM/MRQ）"
            raw_val = ((res.data or {}).get("item") or [{}])[0].get(field)
            if res.status == da.STATUS_FAILED or raw_val is None:
                cit = _citation(res, field, raw_val, "倍", caliber, tol)
                return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                                 actual_value_display="数据异常",
                                                 threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 倍",
                                                 reason_snippet=f"估值数据获取失败：{res.error_detail}", citation=cit)
            val = float(raw_val)
        is_met = _numeric_compare(val, op, float(thr))
        cit = _citation(res, f"item[0].{field}" if not _is_index(cond) else field, val, "倍", caliber, tol)
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=is_met,
            actual_value_display=_fmt(val, "倍"), threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} 倍",
            reason_snippet=f"{cond.target_name} {field} 实测 {val:.2f} 倍，阈值 {OP_SYMBOL.get(op, op.value)} {thr} 倍，条件{'满足' if is_met else '不满足'}",
            citation=cit, gap_pct=_gap_pct(val, op, float(thr)))

    # ---------- 行情类：last_price / pct_chg ----------
    if _is_index(cond):
        res = await da.get_index_quote(cond.target_code)
    else:
        res = await da.get_stock_quote(cond.target_code)
    field_map = {"last_price": "last_price", "pct_chg": "price_change_ratio_pct", "volume": "volume",
                 "turnover": "turnover"}
    field = field_map.get(metric, "last_price")
    unit = {"last_price": "元", "pct_chg": "%", "volume": "股", "turnover": "元"}.get(metric, "元")
    caliber = "扶摇指数行情快照" if _is_index(cond) else "扶摇 A 股行情快照（不复权实时价）"

    raw_val = (res.data.get("item") or [{}])[0].get(field)
    if res.status == da.STATUS_FAILED or raw_val is None:
        reason = f"行情数据获取失败：{res.error_detail}" if res.status == da.STATUS_FAILED \
            else f"行情字段 {field} 为空（可能处于盘前/集合竞价阶段，今日尚无成交数据）"
        cit = _citation(res, field, raw_val, unit, caliber, tol)
        return ConditionEvaluationDetail(condition_id=cond.condition_id, label=cond.label, is_met=None,
                                         actual_value_display="数据异常",
                                         threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} {unit}",
                                         reason_snippet=reason, citation=cit)

    val = float(raw_val)
    if res.status == da.STATUS_CONFLICT:
        cit = _citation(res, f"item[0].{field}", val, unit, caliber, tol)
        conflict = dict(res.conflict_with or {})
        # 用户裁决：按 TRUST_PRIMARY / TRUST_BACKUP / MANUAL 判定，不挂起
        applied = None
        if resolution:
            if resolution.get("mode") == "TRUST_PRIMARY":
                applied = "TRUST_PRIMARY"
            elif resolution.get("mode") == "TRUST_BACKUP" and conflict.get("value") is not None:
                val = float(conflict["value"])
                applied = "TRUST_BACKUP"
            elif (resolution.get("mode") == "MANUAL"
                  and resolution.get("condition_id") == cond.condition_id
                  and isinstance(resolution.get("value"), (int, float))):
                val = float(resolution["value"])
                applied = "MANUAL"
        if applied:
            conflict["resolved_by"] = applied
            cit.conflict_with = conflict
            is_met = _numeric_compare(val, op, float(thr))
            who = {"TRUST_PRIMARY": f"主源 {res.source_name}", "TRUST_BACKUP": f"备源 {conflict.get('source')}",
                   "MANUAL": "人工确认值"}[applied]
            return ConditionEvaluationDetail(
                condition_id=cond.condition_id, label=cond.label, is_met=is_met,
                actual_value_display=_fmt(val, unit),
                threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} {unit}",
                reason_snippet=(f"双源冲突（扶摇 {res.data['item'][0][field]} vs {conflict.get('source')} "
                                f"{conflict.get('value')}，偏差 {conflict.get('diff_pct')}%），已按用户裁决采用{who}={val}判定，"
                                f"条件{'满足' if is_met else '不满足'}"),
                citation=cit, gap_pct=_gap_pct(val, op, float(thr)))
        return ConditionEvaluationDetail(
            condition_id=cond.condition_id, label=cond.label, is_met=None,
            actual_value_display=f"{_fmt(val, unit)}（双源冲突挂起）",
            threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} {unit}",
            reason_snippet=(f"多源冲突：扶摇 {val} {unit} vs {conflict.get('source')} {conflict.get('value')} {unit}"
                            f"（偏差 {conflict.get('diff_pct')}%），阈值 {thr} 处于判定敏感区，系统暂停自动判定。"
                            "可在「数据异常处理卡片」中选择信任数据源或填入确认值"),
            citation=cit)
    is_met = _numeric_compare(val, op, float(thr))
    cit = _citation(res, f"item[0].{field}", val, unit, caliber, tol)
    return ConditionEvaluationDetail(
        condition_id=cond.condition_id, label=cond.label, is_met=is_met,
        actual_value_display=_fmt(val, unit), threshold_display=f"{OP_SYMBOL.get(op, op.value)} {thr} {unit}",
        reason_snippet=f"{cond.target_name} {cond.label.split('，')[0]}实测 {val}{unit if metric != 'pct_chg' else ''}，"
                       f"阈值 {OP_SYMBOL.get(op, op.value)} {thr} {unit}，条件{'满足' if is_met else '不满足'}",
        citation=cit, gap_pct=_gap_pct(val, op, float(thr)))


def _numeric_compare(val: float, op: ComparisonOperator, thr: float) -> bool:
    return {
        ComparisonOperator.GT: val > thr,
        ComparisonOperator.GTE: val >= thr,
        ComparisonOperator.LT: val < thr,
        ComparisonOperator.LTE: val <= thr,
        ComparisonOperator.EQ: abs(val - thr) < 1e-9,
    }[op]


def _gap_pct(val: float, op: ComparisonOperator, thr: float) -> float:
    """正数 = 距离触发还差多少（相对阈值）；负数 = 已越过阈值多少。"""
    if op in (ComparisonOperator.GT, ComparisonOperator.GTE):
        return round((thr - val) / abs(thr) * 100, 2) if thr else 0.0
    if op in (ComparisonOperator.LT, ComparisonOperator.LTE):
        return round((val - thr) / abs(thr) * 100, 2) if thr else 0.0
    return 0.0


def _compose_group(group: RuleGroup, details: list[ConditionEvaluationDetail]) -> bool | None:
    """布尔合成：AND 全真为真；OR 任一真为真；未知(None)按保守传播。"""
    values = [d.is_met for d in details if d.condition_id in {c.condition_id for c in group.conditions}]
    sub_values = [_compose_group(g, details) for g in (group.sub_groups or [])]
    all_vals = values + sub_values
    if group.logical_op.value == "AND":
        if any(v is False for v in all_vals):
            return False
        if any(v is None for v in all_vals):
            return None
        return all_vals and all(all_vals)
    else:  # OR
        if any(v is True for v in all_vals):
            return True
        if any(v is None for v in all_vals):
            return None
        return False


async def evaluate_rule_tree(root: RuleGroup, resolution: dict | None = None) -> EvaluationResult:
    result = EvaluationResult()
    groups = [root] + _flatten_groups(root)
    for g in groups:
        for cond in g.conditions:
            detail = await evaluate_condition(cond, resolution)
            result.condition_details.append(detail)
            cit = detail.citation
            if cit.is_stale:
                result.has_stale = True
            if cit.conflict_with:
                result.has_conflict = True
            if detail.is_met is None:
                result.has_failure = True
            if cit.endpoint_or_tool.startswith("mock") or "离线" in cit.source_name:
                result.has_mock = True
            if "本地缓存回退" in cit.source_name:
                result.has_cache_fallback = True
    result.overall = _compose_group(root, result.condition_details)
    return result


def _flatten_groups(g: RuleGroup) -> list[RuleGroup]:
    out: list[RuleGroup] = []
    for sub in g.sub_groups or []:
        out.append(sub)
        out.extend(_flatten_groups(sub))
    return out


def build_explanation(result: EvaluationResult, rule_name: str, outcome_hint: str) -> StructuredExplanation:
    """确定性生成【事实/推断/不确定性】三段式解释（不经 LLM，保证零幻觉）。"""
    facts: list[str] = []
    for d in result.condition_details:
        c = d.citation
        facts.append(f"[{d.condition_id}] {d.label}：实测 {d.actual_value_display}"
                     f"（来源 {c.source_name} · {c.endpoint_or_tool} · 字段 {c.raw_field_name}"
                     f" · 数据时点 {c.data_timestamp}）")
    inference: list[str] = []
    met_ids = [d.condition_id for d in result.condition_details if d.is_met is True]
    unmet_ids = [d.condition_id for d in result.condition_details if d.is_met is False]
    unknown_ids = [d.condition_id for d in result.condition_details if d.is_met is None]
    if met_ids:
        inference.append(f"已满足条件：{', '.join(met_ids)}")
    if unmet_ids:
        inference.append(f"未满足条件：{', '.join(unmet_ids)}")
    if unknown_ids:
        inference.append(f"无法判定（数据异常/冲突挂起）：{', '.join(unknown_ids)}")
    inference.append(f"规则布尔合成结果：{result.overall}（规则「{rule_name}」）")

    notes: list[str] = []
    if result.has_conflict:
        notes.append("存在多源数据冲突，相关条件已挂起判定并列展示双源数值，请核查原始数据源。")
    if result.has_stale:
        stale_conds = [d.condition_id for d in result.condition_details if d.citation.is_stale]
        notes.append(f"部分行情数据时点滞后超过容忍阈值（{', '.join(stale_conds)}），本次结果仅供参考，不作为正式告警。")
    if result.has_failure:
        notes.append("存在数据缺失或接口失败的条件，系统未静默生成'正常'结论。")
    if result.has_cache_fallback:
        notes.append("部分数据来自本地缓存回退（上游接口失败），请注意缓存时点与实时行情的差异。")
    if result.has_mock:
        notes.append("本次部分数据来自本地高仿真回退数据（离线演示，非实时行情），仅用于演示降级行为。")
    if not notes:
        notes.append("本次巡检各数据源均在新鲜度容忍窗口内，未见冲突。")
    notes.append("本系统仅输出基于用户设定规则的客观监控结论，不构成任何投资建议。")

    headline = outcome_hint
    return StructuredExplanation(
        headline_conclusion=sanitize_text(headline),
        facts_list=[sanitize_text(f) for f in facts],
        inference_list=[sanitize_text(i) for i in inference],
        uncertainty_and_degradation_note=sanitize_text(" ".join(notes)),
    )
