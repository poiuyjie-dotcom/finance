import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class MonitorTask(Base):
    __tablename__ = "monitor_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    current_rule_json: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_dedup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    degraded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 双源冲突的人工裁决：{mode: TRUST_PRIMARY|TRUST_BACKUP|MANUAL, condition_id, value, set_at}
    conflict_resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ---- 状态机常量 ----
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    COOLDOWN = "COOLDOWN"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    ERROR_HALT = "ERROR_HALT"


class TaskRuleVersion(Base):
    __tablename__ = "task_rule_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), index=True)
    version_num: Mapped[int] = mapped_column(Integer)
    rule_json: Mapped[dict] = mapped_column(JSON)
    # NL_INIT / MANUAL_EDIT / NL_REFINE / ROLLBACK
    change_type: Mapped[str] = mapped_column(String(20), default="NL_INIT")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
