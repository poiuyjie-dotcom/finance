"""预置 3 个黄金演示任务：首次启动自动灌入。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MonitorTask, TaskRuleVersion
from .schemas.rule_ast import (
    ComparisonOperator,
    ConditionCategory,
    ConditionLeaf,
    DataSourceType,
    LogicalOperator,
    RuleGroup,
    ScheduleConfig,
    UnifiedMonitorRule,
)


def _c(cid: str, label: str, cat: ConditionCategory, code: str, name: str, metric: str,
       op: ComparisonOperator, thr, unit: str, caliber: str, primary: DataSourceType,
       backup: DataSourceType | None = None) -> ConditionLeaf:
    return ConditionLeaf(condition_id=cid, label=label, category=cat, target_code=code, target_name=name,
                         metric_field=metric, operator=op, threshold_value=thr, unit=unit,
                         statistical_caliber=caliber, primary_source=primary, backup_source=backup)


TASK1 = UnifiedMonitorRule(
    rule_name="宁德时代·多维组合监控",
    original_nl_query="当宁德时代跌破 290 元且换手率大于 3%，或者出现减持/问询函公告，且处于三季报披露前 5 个交易日内提醒我",
    ai_interpretation_summary=("组合监控：OR( AND(价格<290元, 换手率>3%), 公告关键词命中 )，并叠加财报窗口日历条件。"
                               "价格走扶摇行情快照，换手率走 iFinD，公告走 iFinD search_notice，财报日走交易日历推算。"),
    rule_tree=RuleGroup(
        group_id="root", logical_op=LogicalOperator.OR,
        conditions=[
            _c("cond_1", "宁德时代出现减持/问询函相关公告", ConditionCategory.EVENT_ANNOUNCEMENT,
               "300750.SZ", "宁德时代", "announcement_keywords", ComparisonOperator.CONTAINS_ANY,
               ["减持", "问询函"], "篇", "近24小时公告标题与正文关键词匹配（iFinD search_notice）",
               DataSourceType.IFIND_ANNOUNCEMENT),
            _c("cond_2", "处于三季报披露前 5 个交易日窗口内", ConditionCategory.CALENDAR_WINDOW,
               "300750.SZ", "宁德时代", "days_to_earnings", ComparisonOperator.IN_WINDOW, 5, "个交易日",
               "下一定期报告披露日按交易日推算（iFinD 财报日历）", DataSourceType.IFIND_EVENT_CAL),
        ],
        sub_groups=[RuleGroup(
            group_id="grp_1", logical_op=LogicalOperator.AND,
            conditions=[
                _c("cond_3", "宁德时代最新价跌破 290 元", ConditionCategory.PRICE_VALUATION,
                   "300750.SZ", "宁德时代", "last_price", ComparisonOperator.LT, 290.0, "元",
                   "扶摇行情快照（不复权实时价）", DataSourceType.FUYAO_QUOTE),
                _c("cond_4", "宁德时代换手率大于 3%", ConditionCategory.PRICE_VALUATION,
                   "300750.SZ", "宁德时代", "turnover_rate_pct", ComparisonOperator.GT, 3.0, "%",
                   "iFinD 个股日频换手率（自然语言取数）", DataSourceType.IFIND_ANNOUNCEMENT),
            ])],
    ),
    schedule_config=ScheduleConfig(interval_seconds=60, cooldown_minutes=60, dedup_window_minutes=240),
)

TASK2 = UnifiedMonitorRule(
    rule_name="比亚迪·热度与商品联动",
    original_nl_query="比亚迪进入扶摇热榜前 10 名，且碳酸锂主力期货跌幅超过 4% 时提醒我",
    ai_interpretation_summary=("联动监控：AND(热榜排名<=10, 碳酸锂主力涨跌幅<-4%)。"
                               "热榜走扶摇特色数据，期货走 iFinD 期货行情。"),
    rule_tree=RuleGroup(
        group_id="root", logical_op=LogicalOperator.AND,
        conditions=[
            _c("cond_1", "比亚迪进入扶摇热榜前 10 名", ConditionCategory.SENTIMENT_HEAT,
               "002594.SZ", "比亚迪", "hot_rank", ComparisonOperator.LTE, 10, "名",
               "扶摇热榜快照（盘中约每5分钟刷新）", DataSourceType.FUYAO_HOTLIST),
            _c("cond_2", "碳酸锂主力期货跌幅超过 4%", ConditionCategory.SENTIMENT_HEAT,
               "碳酸锂ZL", "碳酸锂", "futures_pct_chg", ComparisonOperator.LT, -4.0, "%",
               "iFinD 期货主力合约日频涨跌幅", DataSourceType.IFIND_COMMODITY),
        ]),
    schedule_config=ScheduleConfig(interval_seconds=120, cooldown_minutes=60, dedup_window_minutes=240),
)

TASK3 = UnifiedMonitorRule(
    rule_name="沪深300·估值与极端波动",
    original_nl_query="沪深300 指数 PE(TTM) 低于 13.5 倍，或单日跌幅超过 2% 时提醒我",
    ai_interpretation_summary=("指数监控：OR(PE_TTM<13.5, 当日涨跌幅<-2%)。"
                               "指数行情走扶摇指数快照，指数 PE 走 iFinD（扶摇估值接口不支持指数）。"),
    rule_tree=RuleGroup(
        group_id="root", logical_op=LogicalOperator.OR,
        conditions=[
            _c("cond_1", "沪深300 指数 PE(TTM) 低于 13.5 倍", ConditionCategory.PRICE_VALUATION,
               "000300.SH", "沪深300", "pe_ttm", ComparisonOperator.LT, 13.5, "倍",
               "iFinD 指数市盈率（TTM，报表公告日基准）", DataSourceType.IFIND_NEWS),
            _c("cond_2", "沪深300 单日跌幅超过 2%", ConditionCategory.PRICE_VALUATION,
               "000300.SH", "沪深300", "pct_chg", ComparisonOperator.LT, -2.0, "%",
               "扶摇指数行情快照（当日涨跌幅）", DataSourceType.FUYAO_QUOTE),
        ]),
    schedule_config=ScheduleConfig(interval_seconds=180, cooldown_minutes=30, dedup_window_minutes=240),
)


def seed_if_empty(db: Session) -> None:
    if db.execute(select(MonitorTask).limit(1)).scalar_one_or_none():
        return
    for rule in (TASK1, TASK2, TASK3):
        task = MonitorTask(title=rule.rule_name, status=MonitorTask.ACTIVE,
                           current_version=1, current_rule_json=rule.model_dump())
        db.add(task)
        db.flush()
        db.add(TaskRuleVersion(task_id=task.id, version_num=1, rule_json=rule.model_dump(),
                               change_type="NL_INIT", change_reason=None,
                               diff_summary={"from_version": 0, "to_version": 1, "changes": [],
                                             "note": "预置演示任务"}))
    db.commit()
