"""任务路由：NL 解析、创建、列表、详情、规则修改、版本、回滚、立即巡检、状态操作。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MonitorTask, TaskExecutionLog, TaskRuleVersion
from ..schemas.rule_ast import UnifiedMonitorRule
from ..schemas.task_schema import (
    NLParseRequest,
    NLParseResponse,
    RuleUpdateRequest,
    TaskCreateRequest,
    TaskDetail,
    TaskStatusAction,
    TaskSummary,
    VersionItem,
)
from ..services import data_adapter as da
from ..services import nl2rule_compiler, state_machine

router = APIRouter()


def _summary(task: MonitorTask, latest_log: TaskExecutionLog | None) -> TaskSummary:
    cooldown_remaining = 0
    if task.cooldown_until:
        # 存储为北京时间无 tz，直接与当前北京时间比较
        cooldown_remaining = max(0, int((task.cooldown_until - da.now_bj().replace(tzinfo=None)).total_seconds()))
    interval = 60
    try:
        interval = int((task.current_rule_json or {}).get("schedule_config", {}).get("interval_seconds", 60))
    except Exception:  # noqa: BLE001
        pass
    return TaskSummary(
        id=task.id, title=task.title, status=task.status, current_version=task.current_version,
        last_executed_at=task.last_executed_at, last_triggered_at=task.last_triggered_at,
        cooldown_until=task.cooldown_until, cooldown_remaining_seconds=cooldown_remaining,
        degraded_reason=task.degraded_reason,
        latest_outcome=latest_log.outcome_type if latest_log else None,
        latest_headline=latest_log.headline if latest_log else None,
        interval_seconds=interval)


def _latest_log(db: Session, task_id: str) -> TaskExecutionLog | None:
    return db.execute(
        select(TaskExecutionLog).where(TaskExecutionLog.task_id == task_id)
        .order_by(TaskExecutionLog.executed_at.desc()).limit(1)
    ).scalar_one_or_none()


@router.post("/tasks/parse-nl", response_model=NLParseResponse)
async def parse_nl(req: NLParseRequest):
    result = await nl2rule_compiler.compile_nl(req.nl_query)
    return NLParseResponse(**result)


@router.post("/tasks", status_code=201)
def create_task(req: TaskCreateRequest, db: Session = Depends(get_db)):
    task = MonitorTask(title=req.rule.rule_name, status=MonitorTask.ACTIVE,
                       current_version=1, current_rule_json=req.rule.model_dump())
    db.add(task)
    db.flush()
    db.add(TaskRuleVersion(task_id=task.id, version_num=1, rule_json=req.rule.model_dump(),
                           change_type="NL_INIT", change_reason=None,
                           diff_summary={"from_version": 0, "to_version": 1, "changes": [],
                                         "note": "自然语言初始化创建"}))
    db.commit()
    return {"id": task.id, "status": task.status, "current_version": task.current_version}


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(status: str = "ALL", db: Session = Depends(get_db)):
    q = select(MonitorTask).order_by(MonitorTask.created_at)
    if status != "ALL":
        q = q.where(MonitorTask.status == status)
    tasks = db.execute(q).scalars().all()
    out = []
    for t in tasks:
        out.append(_summary(t, _latest_log(db, t.id)))
    return out


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(MonitorTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    logs = db.execute(
        select(TaskExecutionLog).where(TaskExecutionLog.task_id == task_id)
        .order_by(TaskExecutionLog.executed_at.desc()).limit(20)).scalars().all()
    version_count = db.execute(
        select(TaskRuleVersion).where(TaskRuleVersion.task_id == task_id)).scalars().all()
    return {
        "task": _summary(task, logs[0] if logs else None).model_dump(),
        "current_rule": task.current_rule_json,
        "recent_logs": [l_to_dict(l) for l in logs],
        "version_count": len(version_count),
    }


def l_to_dict(l: TaskExecutionLog) -> dict:
    # DB 内部存 UTC，序列化时转北京时间展示
    from datetime import timedelta as _td

    executed_bj = (l.executed_at + _td(hours=8)) if l.executed_at else None
    return {
        "log_id": l.id, "task_id": l.task_id, "rule_version": l.rule_version,
        "executed_at": executed_bj.isoformat() if executed_bj else None,
        "outcome_type": l.outcome_type, "task_state_before": l.task_state_before,
        "task_state_after": l.task_state_after, "overall_boolean_result": l.overall_boolean_result,
        "dedup_fingerprint": l.dedup_fingerprint, "cooldown_remaining_seconds": l.cooldown_remaining_seconds,
        "degradation_flag": l.degradation_flag, "condition_details": l.condition_details_json,
        "explanation": l.explanation_json, "headline": l.headline,
    }


@router.put("/tasks/{task_id}/rule")
def update_rule(task_id: str, req: RuleUpdateRequest, db: Session = Depends(get_db)):
    task = db.get(MonitorTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    version = state_machine.update_rule_version(db, task, req.updated_rule, "MANUAL_EDIT", req.change_reason)
    return {"current_version": task.current_version,
            "latest_diff": version.diff_summary,
            "note": "版本已升级；冷却与去重状态已重置，下次巡检将按新规则评估"}


@router.get("/tasks/{task_id}/versions", response_model=list[VersionItem])
def get_versions(task_id: str, db: Session = Depends(get_db)):
    rows = db.execute(select(TaskRuleVersion).where(TaskRuleVersion.task_id == task_id)
                      .order_by(TaskRuleVersion.version_num)).scalars().all()
    return [VersionItem(version_num=r.version_num, change_type=r.change_type, change_reason=r.change_reason,
                        diff_summary=r.diff_summary,
                        created_at=r.created_at or datetime.utcnow()) for r in rows]


@router.post("/tasks/{task_id}/rollback/{version_num}")
def rollback(task_id: str, version_num: int, db: Session = Depends(get_db)):
    task = db.get(MonitorTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    ver = db.execute(select(TaskRuleVersion)
                     .where(TaskRuleVersion.task_id == task_id, TaskRuleVersion.version_num == version_num)
                     ).scalar_one_or_none()
    if not ver:
        raise HTTPException(404, f"版本 v{version_num} 不存在")
    rule = UnifiedMonitorRule.model_validate(ver.rule_json)
    state_machine.update_rule_version(db, task, rule, "ROLLBACK", f"回滚至 v{version_num}")
    return {"current_version": task.current_version, "rolled_back_to": version_num}


@router.post("/tasks/{task_id}/evaluate-now")
async def evaluate_now(task_id: str, bypass_cooldown: bool = False, db: Session = Depends(get_db)):
    task = db.get(MonitorTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    log = await state_machine.run_evaluation(db, task, bypass_cooldown=bypass_cooldown, respect_schedule=False)
    return l_to_dict(log)


@router.post("/tasks/{task_id}/status")
def set_status(task_id: str, req: TaskStatusAction, db: Session = Depends(get_db)):
    task = db.get(MonitorTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if req.action == "PAUSE":
        task.status = MonitorTask.PAUSED
    elif req.action == "RESUME":
        task.status = MonitorTask.ACTIVE
        task.consecutive_failures = 0
        task.degraded_reason = None
    elif req.action == "CLEAR_COOLDOWN":
        # 只解除冷却静默；保留去重指纹，同一事件特征在窗口内仍会被去重拦截
        task.cooldown_until = None
    db.commit()
    return {"id": task.id, "status": task.status, "cooldown_until": task.cooldown_until}
