"""任务生命周期状态机：调度评估、去重指纹、冷却、恢复、版本 Diff。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import MonitorTask, TaskExecutionLog, TaskRuleVersion
from ..schemas.log_schema import StructuredExplanation
from ..schemas.rule_ast import UnifiedMonitorRule
from . import data_adapter as da
from .evaluator import EvaluationResult, build_explanation, evaluate_rule_tree

OUTCOME_TRIGGERED = "TRIGGERED_ALERT"
OUTCOME_NOT_TRIGGERED = "NOT_TRIGGERED_NORMAL"
OUTCOME_DEDUP = "SUPPRESSED_BY_DEDUP"
OUTCOME_COOLDOWN = "SUPPRESSED_BY_COOLDOWN"
OUTCOME_STALE = "DEGRADED_STALE_DATA"
OUTCOME_CONFLICT = "DEGRADED_CONFLICT_HOLD"
OUTCOME_FALLBACK = "DEGRADED_API_FALLBACK"
OUTCOME_RECOVERY = "RECOVERY"
OUTCOME_MARKET_CLOSED = "SKIPPED_MARKET_CLOSED"


def compute_dedup_fingerprint(task_id: str, rule_version: int, details: list) -> str:
    """事件型条件用命中原文，数值型用 THRESHOLD_CROSSED——避免价格波动导致去重失效。"""
    met_features = []
    for cond in sorted(details, key=lambda x: x.condition_id):
        if cond.is_met is not True:
            continue
        cit = cond.citation
        if "notice" in cit.endpoint_or_tool or "news" in cit.endpoint_or_tool:
            raw = cit.raw_value if isinstance(cit.raw_value, list) else str(cit.raw_value)
            met_features.append(f"{cond.condition_id}:{str(raw)[:80]}")
        else:
            met_features.append(f"{cond.condition_id}:NUMERIC_THRESHOLD_CROSSED")
    payload = f"{task_id}:v{rule_version}:{'|'.join(met_features)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _rule_of(task: MonitorTask) -> UnifiedMonitorRule:
    return UnifiedMonitorRule.model_validate(task.current_rule_json)


def _log(task: MonitorTask, outcome: str, result: EvaluationResult | None, explanation: StructuredExplanation,
         state_before: str, rule_version: int, dedup_fp: str | None = None, cooldown_sec: int = 0) -> TaskExecutionLog:
    return TaskExecutionLog(
        task_id=task.id, rule_version=rule_version, executed_at=datetime.utcnow(),
        outcome_type=outcome, task_state_before=state_before, task_state_after=task.status,
        overall_boolean_result=result.overall if result else None,
        dedup_fingerprint=dedup_fp, cooldown_remaining_seconds=cooldown_sec,
        degradation_flag=bool(result and (result.has_stale or result.has_conflict or result.has_failure
                                           or result.has_cache_fallback or result.has_mock)),
        condition_details_json=[d.model_dump() for d in result.condition_details] if result else [],
        explanation_json=explanation.model_dump(),
        headline=explanation.headline_conclusion,
    )


async def run_evaluation(db: Session, task: MonitorTask, bypass_cooldown: bool = False,
                         respect_schedule: bool = True) -> TaskExecutionLog:
    """执行一次完整巡检：评估 -> 状态流转 -> 去重/冷却 -> 写日志。"""
    rule = _rule_of(task)
    sc = rule.schedule_config
    state_before = task.status
    # 数据库统一存 naive 北京时间，避免 aware/naive 混用
    now = da.now_bj().replace(tzinfo=None)

    # 交易日历感知：休市静默（仅公告/新闻类条件仍可评估，此处简化为整体跳过并记录）
    await da.refresh_calendar()
    phase = da.market_phase(now)
    if respect_schedule and sc.trading_calendar_only and phase["phase"] == "NON_TRADING_DAY":
        explanation = StructuredExplanation(
            headline_conclusion="今日为 A 股非交易日，价格类巡检休市静默（公告监控维持运行）。",
            facts_list=[f"交易日历校验：{now.strftime('%Y-%m-%d')} 为非交易日"],
            inference_list=["按调度配置 trading_calendar_only=true，本周期跳过评估。"],
            uncertainty_and_degradation_note="价格指标采用最近交易日收盘快照口径；公告与资讯监控不受休市影响。")
        lg = _log(task, OUTCOME_MARKET_CLOSED, None, explanation, state_before, task.current_version)
        task.last_executed_at = datetime.utcnow()
        db.add(lg)
        db.commit()
        return lg

    # ---- 评估（携带用户对双源冲突的人工裁决）----
    resolution = getattr(task, "conflict_resolution", None)
    result = await evaluate_rule_tree(rule.rule_tree, resolution)

    # ---- 数据健康度决定降级状态 ----
    # 未被用户裁决解决的冲突（已裁决的 conflict 带 resolved_by，不算挂起）；真实接口失败才计熔断
    unresolved_conflict = any(d.is_met is None and d.citation.conflict_with
                              and not d.citation.conflict_with.get("resolved_by")
                              for d in result.condition_details)
    hard_failure = any(d.is_met is None and d.citation.raw_value is None and not d.citation.conflict_with
                       for d in result.condition_details)
    degraded_now = result.has_stale or unresolved_conflict or result.has_failure \
        or result.has_cache_fallback or result.has_mock
    was_degraded = task.status == MonitorTask.DEGRADED

    # ---- 冷却与去重判定：仅当"被满足"的条件不依赖降级数据时才正式触发 ----
    def _cit_degraded(d):
        c = d.citation
        cw = c.conflict_with
        if cw and cw.get("resolved_by"):
            cw = None  # 用户已裁决的冲突不再视为降级
        return c.is_stale or cw or "本地缓存回退" in c.source_name \
            or c.endpoint_or_tool.startswith("mock") or "离线" in c.source_name

    satisfied_on_degraded = any(d.is_met is True and _cit_degraded(d) for d in result.condition_details)
    can_trigger = result.overall is True and not satisfied_on_degraded
    cooldown_remaining = 0
    if task.cooldown_until:
        cooldown_remaining = max(0, int((task.cooldown_until - now).total_seconds()))

    outcome: str
    dedup_fp: str | None = None

    if unresolved_conflict:
        # 双源冲突且未裁决：无论其余条件是否满足，统一挂起并向用户并列展示双源数值
        outcome = OUTCOME_CONFLICT
        if result.overall is True:
            headline = ("多源数据冲突挂起：其余条件虽已满足，但存在双源价格不一致（偏差超阈值），"
                        "系统暂停自动触发——请在「数据异常处理卡片」中选择信任数据源或填入确认值")
        else:
            headline = "多源数据冲突挂起：系统暂停自动结论，并列展示双源数值供核查"
    elif result.overall is None:
        outcome = OUTCOME_FALLBACK
        headline = "无法判定：存在数据缺失或接口失败，系统已暂停自动结论（详见逐条件归因）"
    elif result.overall is True and satisfied_on_degraded:
        if result.has_stale and any(d.citation.is_stale for d in result.condition_details if d.is_met is True):
            outcome = OUTCOME_STALE
            headline = "数据过期降级：条件虽满足但行情时点滞后超容忍阈值，本次不触发正式告警，仅供参考"
        else:
            outcome = OUTCOME_FALLBACK
            headline = ("接口异常降级：本次命中条件依赖本地缓存/离线回退数据，不触发正式告警，"
                        "待上游恢复后自动重算")
    elif can_trigger:
        dedup_fp = compute_dedup_fingerprint(task.id, task.current_version, result.condition_details)
        in_dedup_window = (
            task.last_dedup_hash == dedup_fp
            and task.last_dedup_at
            and (datetime.utcnow() - task.last_dedup_at) < timedelta(minutes=sc.dedup_window_minutes)
        )
        if not bypass_cooldown and cooldown_remaining > 0:
            outcome = OUTCOME_COOLDOWN
            headline = f"条件依然满足，但处于冷却静默期（剩余 {cooldown_remaining // 60} 分 {cooldown_remaining % 60} 秒），本次不重复提醒"
        elif in_dedup_window:
            outcome = OUTCOME_DEDUP
            headline = f"同一命中特征在去重窗口（{sc.dedup_window_minutes} 分钟）内重复出现，已静默拦截（指纹 {dedup_fp}）"
        else:
            outcome = OUTCOME_TRIGGERED
            headline = "条件命中：规则全部/任一条件满足，已生成正式提醒"
            task.last_triggered_at = datetime.utcnow()
            task.last_dedup_hash = dedup_fp
            task.last_dedup_at = datetime.utcnow()
            if sc.cooldown_minutes > 0:
                task.cooldown_until = now + timedelta(minutes=sc.cooldown_minutes)
    else:
        if result.has_cache_fallback or result.has_mock:
            outcome = OUTCOME_FALLBACK
            headline = "未触发（降级口径）：本次基于本地缓存/离线回退数据评估，结论仅供参考，不代表实时正常状态"
        else:
            outcome = OUTCOME_NOT_TRIGGERED
            unmet = [d.label for d in result.condition_details if d.is_met is False]
            headline = "未触发：" + ("；".join(unmet[:2]) if unmet else "部分条件未满足") + "（详见逐条件归因）"

    explanation = build_explanation(result, rule.rule_name, headline)
    if was_degraded and outcome in (OUTCOME_TRIGGERED, OUTCOME_NOT_TRIGGERED):
        explanation.inference_list.insert(0, "[RECOVERY] 数据源已恢复正常新鲜度与一致性，退出降级模式。")

    # ---- 状态流转 ----
    if task.status == MonitorTask.PAUSED and respect_schedule:
        pass  # 暂停任务由调度器跳过，手动评估时仍执行但保持 PAUSED
    if outcome == OUTCOME_TRIGGERED:
        task.status = MonitorTask.TRIGGERED if sc.cooldown_minutes == 0 else MonitorTask.COOLDOWN
        task.consecutive_failures = 0
    elif degraded_now:
        task.status = MonitorTask.DEGRADED
        task.degraded_reason = explanation.uncertainty_and_degradation_note[:500]
        # 只有真实接口失败（拿不到任何数据）才计入熔断；冲突挂起/过期是显式保护行为
        task.consecutive_failures = task.consecutive_failures + (1 if hard_failure else 0)
    elif task.status in (MonitorTask.DEGRADED, MonitorTask.COOLDOWN, MonitorTask.TRIGGERED):
        if was_degraded:
            explanation.inference_list.insert(0, "[RECOVERY] 数据源已恢复正常新鲜度与一致性，退出降级模式。")
            task.status = MonitorTask.ACTIVE
            task.degraded_reason = None
        else:
            task.status = MonitorTask.ACTIVE
    else:
        task.status = MonitorTask.ACTIVE
        task.degraded_reason = None
    if task.consecutive_failures >= 6:
        task.status = MonitorTask.ERROR_HALT
        task.degraded_reason = f"连续 {task.consecutive_failures} 次数据失败，任务熔断，请检查数据源后手动恢复。"

    # 冷却到期自动恢复
    if task.status == MonitorTask.COOLDOWN and task.cooldown_until and now.replace(tzinfo=None) >= task.cooldown_until:
        task.status = MonitorTask.ACTIVE

    task.last_executed_at = datetime.utcnow()
    lg = _log(task, outcome, result, explanation, state_before, task.current_version, dedup_fp, cooldown_remaining)
    db.add(lg)
    db.commit()
    return lg


# ---------------------------------------------------------------- 版本管理
def compute_diff(old_rule: UnifiedMonitorRule, new_rule: UnifiedMonitorRule) -> dict:
    """字段级 Diff：对比两版规则 JSON 的平铺路径。"""
    old_flat = _flatten(old_rule.model_dump())
    new_flat = _flatten(new_rule.model_dump())
    changes = []
    for path in sorted(set(old_flat) | set(new_flat)):
        ov, nv = old_flat.get(path, "<不存在>"), new_flat.get(path, "<不存在>")
        if ov != nv:
            changes.append({"path": path, "old_value": str(ov), "new_value": str(nv)})
    return {"changes": changes, "changed_count": len(changes)}


def _flatten(obj, prefix: str = "") -> dict:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def update_rule_version(db: Session, task: MonitorTask, new_rule: UnifiedMonitorRule,
                        change_type: str, change_reason: str = "") -> TaskRuleVersion:
    """版本升级钩子：版本 +1、生成 Diff、清空旧冷却与旧去重指纹。"""
    old_rule = _rule_of(task)
    diff = compute_diff(old_rule, new_rule)
    task.current_version += 1
    task.current_rule_json = new_rule.model_dump()
    task.title = new_rule.rule_name
    # 关键联动：新规则立即按新阈值重新评估
    task.cooldown_until = None
    task.last_dedup_hash = None
    task.last_dedup_at = None
    task.consecutive_failures = 0
    if task.status in (MonitorTask.ERROR_HALT, MonitorTask.DEGRADED):
        task.status = MonitorTask.ACTIVE
        task.degraded_reason = None
    version = TaskRuleVersion(task_id=task.id, version_num=task.current_version,
                              rule_json=new_rule.model_dump(), change_type=change_type,
                              change_reason=change_reason or None,
                              diff_summary={"from_version": task.current_version - 1,
                                            "to_version": task.current_version, **diff})
    db.add(version)
    db.commit()
    return version
