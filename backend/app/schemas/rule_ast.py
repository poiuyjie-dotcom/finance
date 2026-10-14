from enum import Enum
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field

class ConditionCategory(str, Enum):
    PRICE_VALUATION = "PRICE_VALUATION"
    EVENT_ANNOUNCEMENT = "EVENT_ANNOUNCEMENT"
    CALENDAR_WINDOW = "CALENDAR_WINDOW"
    SENTIMENT_HEAT = "SENTIMENT_HEAT"
    COMPOSITE_PORTFOLIO = "COMPOSITE_PORTFOLIO"

class ComparisonOperator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    CONTAINS_ANY = "CONTAINS_ANY"
    NOT_CONTAINS = "NOT_CONTAINS"
    IN_WINDOW = "IN_WINDOW"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"

class DataSourceType(str, Enum):
    FUYAO_QUOTE = "FUYAO_QUOTE"
    FUYAO_VALUATION = "FUYAO_VALUATION"
    FUYAO_CALENDAR = "FUYAO_CALENDAR"
    FUYAO_HOTLIST = "FUYAO_HOTLIST"
    IFIND_ANNOUNCEMENT = "IFIND_ANNOUNCEMENT"
    IFIND_NEWS = "IFIND_NEWS"
    IFIND_COMMODITY = "IFIND_COMMODITY"
    IFIND_EVENT_CAL = "IFIND_EVENT_CAL"

class ConditionLeaf(BaseModel):
    condition_id: str
    label: str
    category: ConditionCategory
    target_code: str
    target_name: str
    metric_field: str
    operator: ComparisonOperator
    threshold_value: Union[float, int, str, List[str]]
    unit: str
    statistical_caliber: str = "实时日内快照"
    primary_source: DataSourceType
    backup_source: Optional[DataSourceType] = None
    staleness_tolerance_seconds: int = 900

class LogicalOperator(str, Enum):
    AND = "AND"
    OR = "OR"

class RuleGroup(BaseModel):
    group_id: str = "root_group"
    logical_op: LogicalOperator = LogicalOperator.AND
    conditions: List[ConditionLeaf] = Field(..., min_length=1)
    sub_groups: Optional[List["RuleGroup"]] = Field(default_factory=list)

class ScheduleConfig(BaseModel):
    mode: Literal["INTERVAL", "CRON", "TRADING_HOURS_ONLY"] = "TRADING_HOURS_ONLY"
    interval_seconds: int = 60
    trading_calendar_only: bool = True
    cooldown_minutes: int = 60
    dedup_window_minutes: int = 240
    on_data_stale: Literal["DEGRADE_AND_WARN", "SKIP_EVALUATION"] = "DEGRADE_AND_WARN"
    on_data_conflict: Literal["HOLD_AND_ALERT_USER", "USE_PRIMARY_WITH_WARNING"] = "HOLD_AND_ALERT_USER"

class UnifiedMonitorRule(BaseModel):
    rule_name: str
    original_nl_query: str
    ai_interpretation_summary: str
    rule_tree: RuleGroup
    schedule_config: ScheduleConfig
