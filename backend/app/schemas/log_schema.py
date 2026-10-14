"""巡检执行快照与解释器 Schema（Why / Why-Not 归因）。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    source_name: str = Field(..., description="数据源名称，如 扶摇行情API / iFinD MCP")
    endpoint_or_tool: str = Field(..., description="调用的具体接口或 MCP Tool 名")
    raw_field_name: str = Field(..., description="原始返回字段名")
    raw_value: Any = Field(..., description="原始返回值")
    unit: str = Field(..., description="单位")
    statistical_caliber: str = Field(..., description="统计口径")
    data_timestamp: str = Field(..., description="数据生成的原始业务时点")
    fetch_timestamp: str = Field(..., description="系统拉取时点")
    is_stale: bool = False
    staleness_seconds: int = 0
    conflict_with: dict | None = Field(default=None, description="多源冲突时另一数据源的字段值")


class ConditionEvaluationDetail(BaseModel):
    condition_id: str
    label: str
    is_met: bool | None = Field(..., description="True=满足 False=未满足 None=数据异常无法判定")
    actual_value_display: str
    threshold_display: str
    reason_snippet: str
    citation: EvidenceCitation
    gap_pct: float | None = Field(default=None, description="实测值相对阈值的差距百分比，正数代表还差多远")


class StructuredExplanation(BaseModel):
    headline_conclusion: str
    facts_list: list[str] = Field(..., description="【客观事实】100% 可回溯到原始字段的数据陈述")
    inference_list: list[str] = Field(..., description="【规则逻辑推导】布尔合成结论")
    uncertainty_and_degradation_note: str = Field(..., description="【不确定性与降级说明】")


class TaskExecutionSnapshot(BaseModel):
    log_id: str
    task_id: str
    task_title: str = ""
    rule_version: int
    executed_at: datetime
    task_state_before: str
    task_state_after: str
    outcome_type: str
    overall_boolean_result: bool | None = None
    dedup_fingerprint: str | None = None
    cooldown_remaining_seconds: int = 0
    condition_details: list[ConditionEvaluationDetail] = []
    explanation: StructuredExplanation
