"""APScheduler 异步巡检引擎：进程内调度，免 Redis/Celery 依赖。"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import MonitorTask
from .state_machine import run_evaluation

scheduler = AsyncIOScheduler(timezone=config.TZ_NAME)


async def tick() -> None:
    """全局巡检：遍历非暂停/非熔断任务，按各自 interval_seconds 判断是否到期。"""
    db: Session = SessionLocal()
    try:
        tasks = db.execute(select(MonitorTask)).scalars().all()
        now = datetime.utcnow()
        for task in tasks:
            if task.status in (MonitorTask.PAUSED, MonitorTask.ERROR_HALT):
                continue
            interval = 60
            try:
                interval = int((task.current_rule_json or {}).get("schedule_config", {}).get("interval_seconds", 60))
            except Exception:  # noqa: BLE001
                pass
            due = task.last_executed_at is None or (now - task.last_executed_at) >= timedelta(seconds=interval)
            if due:
                try:
                    await run_evaluation(db, task)
                except Exception as e:  # noqa: BLE001
                    task.consecutive_failures += 1
                    if task.consecutive_failures >= 6:
                        task.status = MonitorTask.ERROR_HALT
                        task.degraded_reason = f"调度异常熔断：{e}"
                    db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(tick, "interval", seconds=config.SCHEDULER_TICK_SECONDS, id="global_tick",
                          max_instances=1, coalesce=True)
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
