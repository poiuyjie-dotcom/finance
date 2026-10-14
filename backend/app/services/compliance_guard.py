"""合规护栏：前置输入拦截 + 后置输出清洗，确定性正则规则（不经 LLM）。"""
from __future__ import annotations

import re

# 纯违规：索要预测/荐股/收益承诺，且不含可提取的客观监控条件
HARD_REJECT_PATTERNS = [
    r"(推荐|哪只?|什么)([^。]{0,12})(必涨|涨停|牛股|翻倍|暴涨)",
    r"(预测|预估|判断)([^。]{0,10})(明天|次日|未来)[^。]{0,8}(涨|跌|走势)",
    r"(帮|给我).{0,6}(选股|荐股|推荐买)",
    r"(稳赚|保本|收益承诺|包赚)",
    r"(内幕|老鼠仓|庄家动向)",
]

# 主观交易词：出现在含客观条件的句子里时剥离，而非拒绝
STRIP_TERMS = ["满仓", "抄底", "梭哈", "加仓", "清仓", "止损", "止盈", "买入", "卖出", "建仓",
               "建议买", "建议卖", "逃顶", "追涨"]

# 后置输出清洗词（展示文本中禁止出现）
OUTPUT_FORBIDDEN = ["建议买入", "建议卖出", "建议加仓", "建议清仓", "必涨", "必跌", "稳赚",
                    "目标价看高至", "满仓", "抄底", "梭哈"]

AUDIT_LOG: list[dict] = []


def check_input(text: str) -> dict:
    """前置拦截。返回 {passed, rejected_reason, stripped_terms, cleaned_text}。"""
    stripped = [t for t in STRIP_TERMS if t in text]
    cleaned = text
    for t in stripped:
        cleaned = cleaned.replace(t, "")
    cleaned = re.sub(r"(时)?提醒我。?$", r"\1提醒我", cleaned) if cleaned.endswith("。") else cleaned

    for p in HARD_REJECT_PATTERNS:
        m = re.search(p, text)
        if m:
            has_objective = bool(re.search(r"(跌破|低于|高于|超过|大于|小于|到达|涨到|跌到|以上|以下|\d+(\.\d+)?\s*(元|倍|%))", text))
            if has_objective:
                # 混合意图：剥离主观指令，保留客观条件
                AUDIT_LOG.append({"rule": "MIXED_INTENT_STRIP", "pattern": p, "input": text[:100]})
                return {"passed": True, "rejected_reason": "",
                        "stripped_terms": stripped + [m.group()],
                        "cleaned_text": cleaned}
            AUDIT_LOG.append({"rule": "HARD_REJECT", "pattern": p, "input": text[:100]})
            return {"passed": False,
                    "rejected_reason": ("本产品不提供涨跌预测、选股推荐或收益承诺。"
                                        "请改为客观指标监控，例如：「当宁德时代(300750.SZ)最新价跌破 200 元时提醒我」。"),
                    "stripped_terms": [], "cleaned_text": ""}
    return {"passed": True, "rejected_reason": "", "stripped_terms": stripped, "cleaned_text": cleaned}


def sanitize_text(text: str) -> str:
    """后置输出清洗：替换违规词为合规表述。"""
    out = text
    for w in OUTPUT_FORBIDDEN:
        if w in out:
            out = out.replace(w, "（该表述已按合规要求过滤）")
            AUDIT_LOG.append({"rule": "OUTPUT_SANITIZE", "word": w})
    return out
