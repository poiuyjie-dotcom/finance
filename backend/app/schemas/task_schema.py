"""任务 CRUD、NL 解析、状态操作的请求/响应 Schema。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .rule_ast import UnifiedMonitorRule


class NLParseRequest(BaseModel):
    nl_query: str = Field(..., min_length=2, max_length=500)


class NLParseResponse(BaseModel):
    compliance_passed: bool
    compliance_notice: str = ""
    compliance_stripped_terms: list[str] = []
    rejected_reason: str = ""
    used_llm: bool = False
    draft_rule: UnifiedMonitorRule | None = None


class TaskCreateRequest(BaseModel):
    rule: UnifiedMonitorRule


class TaskStatusAction(BaseModel):
    action: Literal["PAUSE", "RESUME", "CLEAR_COOLDOWN"]


class RuleUpdateRequest(BaseModel):
    updated_rule: UnifiedMonitorRule
    change_reason: str = ""


class VersionItem(BaseModel):
    version_num: int
    change_type: str
    change_reason: str | None = None
    diff_summary: dict | None = None
    created_at: datetime


class TaskSummary(BaseModel):
    id: str
    title: str
    status: str
    current_version: int
    last_executed_at: datetime | None = None
    last_triggered_at: datetime | None = None
    cooldown_until: datetime | None = None
    cooldown_remaining_seconds: int = 0
    degraded_reason: str | None = None
    latest_outcome: str | None = None
    latest_headline: str | None = None
    interval_seconds: int = 60


class TaskDetail(TaskSummary):
    current_rule: UnifiedMonitorRule
    version_count: int = 1


class FaultInjectRequest(BaseModel):
    mode: Literal["NORMAL", "STALE_DATA", "SOURCE_CONFLICT", "API_TIMEOUT"]
    target_code: str = ""
