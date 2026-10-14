import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TaskExecutionLog(Base):
    __tablename__ = "task_execution_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    task_id: Mapped[str] = mapped_column(String(32), index=True)
    rule_version: Mapped[int] = mapped_column(Integer)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # TRIGGERED_ALERT / NOT_TRIGGERED_NORMAL / SUPPRESSED_BY_DEDUP /
    # SUPPRESSED_BY_COOLDOWN / DEGRADED_STALE_DATA / DEGRADED_CONFLICT_HOLD /
    # DEGRADED_API_FALLBACK / RECOVERY / SKIPPED_MARKET_CLOSED
    outcome_type: Mapped[str] = mapped_column(String(40))
    task_state_before: Mapped[str] = mapped_column(String(20))
    task_state_after: Mapped[str] = mapped_column(String(20))
    overall_boolean_result: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dedup_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cooldown_remaining_seconds: Mapped[int] = mapped_column(Integer, default=0)
    degradation_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    condition_details_json: Mapped[list] = mapped_column(JSON, default=list)
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
