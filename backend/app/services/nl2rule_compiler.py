"""自然语言 -> 统一规则 AST 编译器。

双通道设计：
1. 确定性解析器（默认）：关键词/正则抽取，零幻觉、可复现，覆盖价格/涨跌幅/换手率/估值/
   热榜/公告/财报窗口/期货联动等主流表达。
2. LLM 增强通道（可选）：配置 LLM_API_KEY 后启用，输出仍强制经 Pydantic 校验 +
   合规后置清洗，校验失败自动回退确定性解析器。

编译结果只是一份"草稿规则"，交给前端可视化检查、修改后才创建任务；
所有数值判定一律由 evaluator.py 的确定性代码执行。
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from .. import config
from ..schemas.rule_ast import (
    ComparisonOperator,
    ConditionCategory,
    ConditionLeaf,
    DataSourceType,
    LogicalOperator,
    RuleGroup,
    ScheduleConfig,
    UnifiedMonitorRule,
)
from .compliance_guard import check_input

NAME2CODE = {
    "宁德时代": "300750.SZ", "比亚迪": "002594.SZ", "贵州茅台": "600519.SH",
    "平安银行": "000001.SZ", "隆基绿能": "601012.SH", "中远海控": "601919.SH",
    "沪深300": "000300.SH", "沪深300指数": "000300.SH", "上证指数": "000001.SH",
    "深证成指": "399001.SZ", "创业板指": "399006.SZ", "中证500": "000905.SH", "中证1000": "000852.SH",
}
CODE2NAME = {v: k for k, v in NAME2CODE.items()}
INDEX_CODES = {"000300.SH", "000001.SH", "000905.SH", "000852.SH", "399001.SZ", "399006.SZ"}
FUTURES_VARIETIES = ["碳酸锂", "螺纹钢", "原油", "黄金", "铜", "铁矿石", "生猪", "焦煤", "焦炭", "PTA"]

ANN_KEYWORD_POOL = ["减持", "增持", "回购", "问询函", "立案", "调查", "业绩预亏", "预亏", "业绩预告",
                    "停牌", "复牌", "解禁", "质押", "违规", "处罚", "退市风险"]


def _mk(cond_id: str, label: str, category: ConditionCategory, code: str, name: str,
        metric: str, op: ComparisonOperator, thr, unit: str, caliber: str,
        primary: DataSourceType, backup: DataSourceType | None = None) -> ConditionLeaf:
    return ConditionLeaf(condition_id=cond_id, label=label, category=category, target_code=code,
                          target_name=name, metric_field=metric, operator=op, threshold_value=thr,
                          unit=unit, statistical_caliber=caliber, primary_source=primary, backup_source=backup)


def _find_target(text: str) -> tuple[str, str] | None:
    for name in sorted(NAME2CODE, key=len, reverse=True):
        if name in text:
            return NAME2CODE[name], name.rstrip("指数")
    return None


def _num(x: str) -> float:
    return float(x.replace(",", ""))


def parse_nl_to_rule(nl_query: str, cleaned_query: str = "") -> tuple[UnifiedMonitorRule, list[str], bool]:
    """确定性解析。返回 (规则, 提示列表, 是否成功)。"""
    text = cleaned_query or nl_query
    notes: list[str] = []
    target = _find_target(text)
    futures_cond = None

    # 期货品种独立探测（可与股票条件共存）
    for v in FUTURES_VARIETIES:
        if v in text:
            m = re.search(rf"{v}[^。，；]*?(?:跌幅|下跌)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", text)
            if m:
                futures_cond = _mk("cond_fut", f"{v}主力期货跌幅超过{_num(m.group(1))}%",
                                   ConditionCategory.SENTIMENT_HEAT, f"{v}ZL", v, "futures_pct_chg",
                                   ComparisonOperator.LT, -_num(m.group(1)), "%",
                                   "iFinD 期货主力合约日频涨跌幅", DataSourceType.IFIND_COMMODITY)
            else:
                m2 = re.search(rf"{v}[^。，；]*?(?:涨幅|上涨)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", text)
                if m2:
                    futures_cond = _mk("cond_fut", f"{v}主力期货涨幅超过{_num(m2.group(1))}%",
                                       ConditionCategory.SENTIMENT_HEAT, f"{v}ZL", v, "futures_pct_chg",
                                       ComparisonOperator.GT, _num(m2.group(1)), "%",
                                       "iFinD 期货主力合约日频涨跌幅", DataSourceType.IFIND_COMMODITY)
            break

    if not target:
        if futures_cond:
            rule = UnifiedMonitorRule(
                rule_name=text[:30],
                original_nl_query=nl_query,
                ai_interpretation_summary=("已提取商品期货联动监控条件。本系统仅做客观指标监控，"
                                           "不提供涨跌预测或买卖建议。"),
                rule_tree=RuleGroup(group_id="root", logical_op=LogicalOperator.AND, conditions=[futures_cond]),
                schedule_config=ScheduleConfig())
            return rule, notes, True
        return UnifiedMonitorRule(rule_name="", original_nl_query=nl_query,
                                  ai_interpretation_summary="", rule_tree=RuleGroup(
                                      conditions=[_mk("cond_1", "占位", ConditionCategory.PRICE_VALUATION,
                                                      "000000.SH", "未知", "last_price", ComparisonOperator.GT,
                                                      0, "元", "", DataSourceType.FUYAO_QUOTE)]),
                                  schedule_config=ScheduleConfig()), \
            ["未能从输入中识别出可监控的标的或指标，请尝试明确标的名称与量化条件（如「宁德时代跌破200元」）。"], False

    code, name = target
    is_index = code in INDEX_CODES

    # OR 分支切分
    branches = re.split(r"或者|或｜或者的话|；|;", text)
    and_conditions: list[ConditionLeaf] = []
    or_conditions: list[ConditionLeaf] = []

    def parse_atomic(seg: str) -> ConditionLeaf | None:
        # 含期货品种的句子交给顶层 futures_cond 处理，避免重复建条件
        if any(v in seg for v in FUTURES_VARIETIES):
            return None
        # 跌破/低于 X 元
        m = re.search(r"(?:跌破|低于|小于|跌到|回落到)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*(?:元|块)", seg)
        if m:
            thr = _num(m.group(1))
            return _mk("", f"{name}最新价跌破 {thr:g} 元", ConditionCategory.PRICE_VALUATION, code, name,
                       "last_price", ComparisonOperator.LT, thr, "元", "扶摇行情快照（不复权实时价）",
                       DataSourceType.FUYAO_QUOTE, DataSourceType.FUYAO_QUOTE)
        # 高于/涨到 X 元
        m = re.search(r"(?:涨到|高于|大于|超过|升破|突破)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*(?:元|块)", seg)
        if m:
            thr = _num(m.group(1))
            return _mk("", f"{name}最新价高于 {thr:g} 元", ConditionCategory.PRICE_VALUATION, code, name,
                       "last_price", ComparisonOperator.GT, thr, "元", "扶摇行情快照（不复权实时价）",
                       DataSourceType.FUYAO_QUOTE, DataSourceType.FUYAO_QUOTE)
        # 涨幅超过 X%
        m = re.search(r"涨幅[^。，；]*?(?:超过|大于|高于)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m:
            thr = _num(m.group(1))
            return _mk("", f"{name}当日涨幅超过 {thr:g}%", ConditionCategory.PRICE_VALUATION, code, name,
                       "pct_chg", ComparisonOperator.GT, thr, "%", "扶摇行情快照（当日涨跌幅）",
                       DataSourceType.FUYAO_QUOTE)
        # 跌幅超过 X%
        m = re.search(r"跌幅[^。，；]*?(?:超过|大于|高于)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m:
            thr = -_num(m.group(1))
            return _mk("", f"{name}当日跌幅超过 {abs(thr):g}%", ConditionCategory.PRICE_VALUATION, code, name,
                       "pct_chg", ComparisonOperator.LT, thr, "%", "扶摇行情快照（当日涨跌幅）",
                       DataSourceType.FUYAO_QUOTE)
        # 单日跌/涨 X%
        m = re.search(r"(?:单日|当日)?(?:下跌|大跌|跌幅)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m and "换手" not in seg[:seg.find(m.group(1))]:
            thr = -_num(m.group(1))
            return _mk("", f"{name}当日跌幅超过 {abs(thr):g}%", ConditionCategory.PRICE_VALUATION, code, name,
                       "pct_chg", ComparisonOperator.LT, thr, "%", "扶摇行情快照（当日涨跌幅）",
                       DataSourceType.FUYAO_QUOTE)
        m = re.search(r"(?:单日|当日)?(?:上涨|大涨|涨幅)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m and "换手" not in seg[:seg.find(m.group(1))]:
            thr = _num(m.group(1))
            return _mk("", f"{name}当日涨幅超过 {thr:g}%", ConditionCategory.PRICE_VALUATION, code, name,
                       "pct_chg", ComparisonOperator.GT, thr, "%", "扶摇行情快照（当日涨跌幅）",
                       DataSourceType.FUYAO_QUOTE)
        # 换手率
        m = re.search(r"换手率[^。，；]*?(?:大于|超过|高于|达到)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m:
            thr = _num(m.group(1))
            return _mk("", f"{name}换手率大于 {thr:g}%", ConditionCategory.PRICE_VALUATION, code, name,
                       "turnover_rate_pct", ComparisonOperator.GT, thr, "%", "iFinD 个股日频换手率（自然语言取数）",
                       DataSourceType.IFIND_ANNOUNCEMENT)
        # PE
        m = re.search(r"(?:PE|pe|市盈率)[^。，；]*?(?:低于|小于|跌破)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*(?:倍)?", seg)
        if m:
            thr = _num(m.group(1))
            if is_index:
                return _mk("", f"{name}指数PE(TTM)低于 {thr:g} 倍", ConditionCategory.PRICE_VALUATION, code, name,
                           "pe_ttm", ComparisonOperator.LT, thr, "倍", "iFinD 指数市盈率（TTM）",
                           DataSourceType.IFIND_NEWS)
            return _mk("", f"{name}PE(TTM)低于 {thr:g} 倍", ConditionCategory.PRICE_VALUATION, code, name,
                       "pe_ttm", ComparisonOperator.LT, thr, "倍", "扶摇估值快照（TTM）",
                       DataSourceType.FUYAO_VALUATION)
        m = re.search(r"(?:PE|pe|市盈率)[^。，；]*?(?:高于|大于|超过)[^。，；]*?([0-9]+(?:\.[0-9]+)?)\s*(?:倍)?", seg)
        if m:
            thr = _num(m.group(1))
            if is_index:
                return _mk("", f"{name}指数PE(TTM)高于 {thr:g} 倍", ConditionCategory.PRICE_VALUATION, code, name,
                           "pe_ttm", ComparisonOperator.GT, thr, "倍", "iFinD 指数市盈率（TTM）",
                           DataSourceType.IFIND_NEWS)
            return _mk("", f"{name}PE(TTM)高于 {thr:g} 倍", ConditionCategory.PRICE_VALUATION, code, name,
                       "pe_ttm", ComparisonOperator.GT, thr, "倍", "扶摇估值快照（TTM）",
                       DataSourceType.FUYAO_VALUATION)
        # 热榜前 N
        m = re.search(r"热榜[^。，；]*?前\s*([0-9]+)\s*名", seg) or re.search(
            r"热榜[^。，；]*?(?:排名|进入)[^。，；]*?([0-9]+)\s*名", seg)
        if m:
            thr = int(m.group(1))
            return _mk("", f"{name}进入扶摇热榜前 {thr} 名", ConditionCategory.SENTIMENT_HEAT, code, name,
                       "hot_rank", ComparisonOperator.LTE, thr, "名", "扶摇热榜快照（盘中约每5分钟刷新）",
                       DataSourceType.FUYAO_HOTLIST)
        # 公告关键词
        kws = [k for k in ANN_KEYWORD_POOL if k in seg]
        m = re.search(r"(?:出现|发布|收到|公告|披露)[^。，；]*?(减持|回购|问询函|立案|调查|业绩预亏|预亏|解禁|停牌|处罚|违规)", seg)
        if m or kws:
            found = [m.group(1)] if m else []
            for k in kws:
                if k not in found:
                    found.append(k)
            return _mk("", f"{name}出现{'/'.join(found[:3])}相关公告", ConditionCategory.EVENT_ANNOUNCEMENT,
                       code, name, "announcement_keywords", ComparisonOperator.CONTAINS_ANY, found[:3], "篇",
                       "近24小时公告标题与正文关键词匹配（iFinD search_notice）", DataSourceType.IFIND_ANNOUNCEMENT)
        # 财报窗口
        m = re.search(r"(?:财报|三季报|季报|年报|半年报)[^。，；]*?(?:前|之前|披露前)[^。，；]*?([0-9]+)\s*个?交易日", seg) or \
            re.search(r"(?:财报|三季报|季报|年报|半年报)[^。，；]*?([0-9]+)\s*个?交易日内?", seg)
        if m:
            thr = int(m.group(1))
            return _mk("", f"处于财报披露前 {thr} 个交易日窗口内", ConditionCategory.CALENDAR_WINDOW, code, name,
                       "days_to_earnings", ComparisonOperator.IN_WINDOW, thr, "个交易日",
                       "下一定期报告披露日按交易日推算", DataSourceType.IFIND_EVENT_CAL)
        return None

    # 分支组装：先按 或者/或/； 切 OR 分支，分支内按 且/， 切 AND 条件
    branches = re.split(r"或者|；|;|或(?![者多许])", text)
    branches = [b for b in (br.strip() for br in branches) if b]
    if len(branches) <= 1:
        branches = [text]

    branch_conds: list[list[ConditionLeaf]] = []
    for branch in branches:
        segs = re.split(r"且|并且|同时|，|,", branch)
        conds = [c for seg in segs if (c := parse_atomic(seg))]
        branch_conds.append(conds)
    # 期货条件并入其出现的分支（或独立成支）
    if futures_cond:
        appended = False
        for i, br in enumerate(branches):
            if any(v in br for v in FUTURES_VARIETIES) and i < len(branch_conds):
                branch_conds[i].append(futures_cond)
                appended = True
                break
        if not appended:
            branch_conds.append([futures_cond])

    total = sum(len(c) for c in branch_conds)
    if total == 0:
        return UnifiedMonitorRule(rule_name="", original_nl_query=nl_query,
                                  ai_interpretation_summary="", rule_tree=RuleGroup(
                                      conditions=[_mk("cond_1", "占位", ConditionCategory.PRICE_VALUATION,
                                                      code, name, "last_price", ComparisonOperator.GT, 0, "元",
                                                      "", DataSourceType.FUYAO_QUOTE)]),
                                  schedule_config=ScheduleConfig()), \
            ["识别到标的但未提取出量化条件，请在规则编辑器中手动补充阈值。"], False

    # 条件统一重编号
    i = 0
    for conds in branch_conds:
        for c in conds:
            i += 1
            c.condition_id = f"cond_{i}"

    if len(branch_conds) == 1:
        root = RuleGroup(group_id="root", logical_op=LogicalOperator.AND, conditions=branch_conds[0])
        has_or = False
    else:
        # 多分支：每支包成 AND 子组，顶层 OR；只有 1 个条件的支直接挂顶层
        flat_conds = [conds[0] for conds in branch_conds if len(conds) == 1]
        sub_groups = [RuleGroup(group_id=f"grp_{n + 1}", logical_op=LogicalOperator.AND, conditions=conds)
                      for n, conds in enumerate(branch_conds) if len(conds) > 1]
        root = RuleGroup(group_id="root", logical_op=LogicalOperator.OR,
                         conditions=flat_conds or [
                             _mk("cond_x", "占位", ConditionCategory.PRICE_VALUATION, code, name, "last_price",
                                 ComparisonOperator.GT, 0, "元", "", DataSourceType.FUYAO_QUOTE)],
                         sub_groups=sub_groups or None)
        has_or = True

    summary = (f"已将您的关注点编译为结构化监控规则：标的 {name}({code})，共 {i} 个原子条件"
               f"（价格/涨跌幅、换手率、估值、公告事件、日历窗口、热度与期货联动），"
               f"顶层逻辑为 {'任一满足(OR)' if has_or else '全部满足(AND)'}。"
               "请在下方编辑器检查并按需修改阈值与算子。本系统仅监控客观指标，不提供涨跌预测或买卖建议。")

    rule = UnifiedMonitorRule(rule_name=f"{name}·多维监控", original_nl_query=nl_query,
                              ai_interpretation_summary=summary, rule_tree=root,
                              schedule_config=ScheduleConfig())
    return rule, notes, True


# ---------------------------------------------------------------- LLM 增强通道（可选）
_llm_status = {"status": "UNKNOWN", "last_sync": "", "last_error": "", "latency_ms": None}
_llm_status_config = None


def get_llm_status() -> dict:
    global _llm_status_config
    signature = (config.LLM_API_KEY, config.LLM_BASE_URL, config.LLM_MODEL)
    if signature != _llm_status_config:
        _llm_status.update(status="UNKNOWN", last_sync="", last_error="", latency_ms=None)
        _llm_status_config = signature
    return {"enabled": all(signature), "model": config.LLM_MODEL, **_llm_status}


async def _llm_compile(nl_query: str) -> UnifiedMonitorRule | None:
    if not get_llm_status()["enabled"]:
        return None
    import json

    import httpx

    from .compliance_guard import sanitize_text
    prompt = f"""你是"可配置投资监控与风险雷达"的规则编译器。请把用户自然语言编译为严格符合
UnifiedMonitorRule JSON Schema 的监控规则树。标的代码标准化：宁德时代->300750.SZ，
比亚迪->002594.SZ，贵州茅台->600519.SH，沪深300->000300.SH，碳酸锂主力->品种名"碳酸锂"。
枚举值必须使用：ConditionCategory[PRICE_VALUATION,EVENT_ANNOUNCEMENT,CALENDAR_WINDOW,SENTIMENT_HEAT,COMPOSITE_PORTFOLIO]；
ComparisonOperator[>,>=,<,<=,==,CONTAINS_ANY,NOT_CONTAINS,IN_WINDOW,OUTSIDE_WINDOW]；
DataSourceType[FUYAO_QUOTE,FUYAO_VALUATION,FUYAO_CALENDAR,FUYAO_HOTLIST,IFIND_ANNOUNCEMENT,IFIND_NEWS,IFIND_COMMODITY,IFIND_EVENT_CAL]；
换手率用 metric_field=turnover_rate_pct(主源IFIND_ANNOUNCEMENT)；指数PE用 pe_ttm(主源IFIND_NEWS)；
公告关键词用 announcement_keywords+CONTAINS_ANY；财报窗口用 days_to_earnings+IN_WINDOW。
严禁包含任何预测、买卖建议表述。只输出 JSON，不要输出其他文字。
用户输入：{nl_query}"""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=40) as ac:
            r = await ac.post(f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                              headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                              json={"model": config.LLM_MODEL, "temperature": 0,
                                    "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(json)?|```$", "", content, flags=re.M).strip()
            rule = UnifiedMonitorRule.model_validate(json.loads(content))
            rule.original_nl_query = nl_query
            rule.ai_interpretation_summary = sanitize_text(rule.ai_interpretation_summary)
            _llm_status.update(status="HEALTHY", last_error="",
                               last_sync=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                               latency_ms=round((time.perf_counter() - started) * 1000))
            return rule
    except Exception as exc:  # noqa: BLE001
        # Keep credentials, provider URLs and model output out of the public health response.
        reason = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
        _llm_status.update(status="ERROR", last_error=reason,
                           last_sync=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                           latency_ms=round((time.perf_counter() - started) * 1000))
        return None


async def compile_nl(nl_query: str) -> dict:
    """总入口：确定性正则前置拦截 -> Jev 语义护栏（可选）-> LLM(可选) -> 确定性解析兜底。

    Jev 只提供校准概率，拦截/放行决策全部由代码规则执行；Jev 不可用时静默回退正则-only。
    """
    guard = check_input(nl_query)
    jev_info: dict | None = None

    # ---- Jev 语义第二道闸（可选，与正则独立并行判定，结论由代码合并）----
    from . import jev_client
    if jev_client.is_enabled():
        sem = await jev_client.semantic_compliance_check(nl_query)
        if sem is not None:
            jev_info = sem
            from .compliance_guard import AUDIT_LOG
            AUDIT_LOG.append({"rule": "JEV_SEMANTIC_CHECK", "input": nl_query[:100],
                              "intent": sem["intent"], "wants_prediction": sem["wants_prediction"]})
    jev_reject = bool(jev_info and jev_info["intent"] == "pure_advice_request"
                      and (jev_info["wants_prediction"] or 0) > 0.8)

    if not guard["passed"] or jev_reject:
        parts = []
        if not guard["passed"]:
            parts.append("确定性规则护栏：" + guard["rejected_reason"])
        if jev_reject:
            parts.append(f"语义护栏（Jev 系统一模型）：判定为纯预测/荐股诉求"
                         f"（预测意图概率 {jev_info['wants_prediction']:.2f}，意图置信度 {jev_info['intent_confidence']:.2f}）")
        notice = "；".join(parts)
        return {"compliance_passed": False, "compliance_notice": notice,
                "compliance_stripped_terms": [], "rejected_reason": notice,
                "used_llm": False, "draft_rule": None, "jev": jev_info}

    notice = ""
    if guard["stripped_terms"]:
        notice = (f"检测到主观交易表述「{'、'.join(guard['stripped_terms'])}」，已自动剥离。"
                  "本系统不提供抄底、买卖等建议，仅保留客观监控条件。")
    if jev_info and jev_info["intent"] == "mixed" and not guard["stripped_terms"]:
        notice = (f"语义护栏（Jev）判定为混合意图（置信度 {jev_info['intent_confidence']:.2f}），"
                  "已仅保留客观监控条件，剥离主观交易表述。")
    elif jev_info and jev_info["intent"] == "objective_monitor" and not notice:
        notice = f"语义护栏（Jev）确认输入为客观监控意图（预测意图概率 {(jev_info['wants_prediction'] or 0):.2f}）。"

    rule = await _llm_compile(guard["cleaned_text"] or nl_query)
    used_llm = rule is not None
    if rule is None:
        rule, notes, ok = parse_nl_to_rule(nl_query, guard["cleaned_text"])
        if not ok:
            notice = (notice + " " + " ".join(notes)).strip()
        if not ok and not guard["stripped_terms"]:
            return {"compliance_passed": True, "compliance_notice": notice or "解析提示见 ai_interpretation_summary",
                    "compliance_stripped_terms": guard["stripped_terms"], "rejected_reason": "",
                    "used_llm": False, "draft_rule": rule, "jev": jev_info}
    return {"compliance_passed": True, "compliance_notice": notice,
            "compliance_stripped_terms": guard["stripped_terms"], "rejected_reason": "",
            "used_llm": used_llm, "draft_rule": rule, "jev": jev_info}
