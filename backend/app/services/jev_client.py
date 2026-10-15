"""Jev（TypeSafe System One）客户端：结构化语义判断，含超时、TTL 缓存与静默降级。

定位边界：Jev 只承担「模糊语义判断」（合规意图识别、公告情绪归因），
所有数值比较与触发判定仍由确定性引擎执行；Jev 不可用时调用方自动回退，主链路不受影响。
"""
from __future__ import annotations

import hashlib
import time

import httpx

from .. import config

_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_TIMEOUT = httpx.Timeout(12.0, connect=6.0)
_CACHE_TTL = 600  # 相同 state+问题 10 分钟内复用，节省配额
_cache: dict[str, tuple[float, dict]] = {}
_status: dict = {"status": "UNKNOWN", "last_sync": "", "last_error": ""}
_status_config = None


def get_status() -> dict:
    global _status_config
    signature = (config.JEV_API_KEY, config.JEV_MODEL)
    if signature != _status_config:
        _status.update(status="UNKNOWN", last_sync="", last_error="")
        _cache.clear()
        _status_config = signature
    return dict(_status)


def is_enabled() -> bool:
    return bool(config.JEV_API_KEY)


def _cache_key(state, questions: dict) -> str:
    payload = repr(state) + repr(sorted(questions.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def jev_evaluate(state, questions: dict) -> dict | None:
    """调用 Jev。返回 {answers: {...}, model} 或 None（未配置/失败/超时——调用方静默回退）。"""
    get_status()
    if not config.JEV_API_KEY:
        return None
    key = _cache_key(state, questions)
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as ac:
            r = await ac.post(_ENDPOINT, headers={
                "Authorization": f"Bearer {config.JEV_API_KEY}",
                "Content-Type": "application/json",
            }, json={"state": state, "model": config.JEV_MODEL, "questions": questions})
            r.raise_for_status()
            body = r.json()
        answers = body.get("answers") or {}
        if not answers:
            raise RuntimeError("answers 为空")
        _status.update(status="HEALTHY", last_sync=time.strftime("%Y-%m-%dT%H:%M:%S+08:00",
                                                                 time.gmtime(time.time() + 8 * 3600)),
                       last_error="")
        _cache[key] = (now, body)
        return body
    except Exception as e:  # noqa: BLE001
        _status.update(status="ERROR", last_sync=time.strftime("%Y-%m-%dT%H:%M:%S+08:00",
                                                               time.gmtime(time.time() + 8 * 3600)),
                       last_error=f"{type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------- 两个封装好的业务问题
async def semantic_compliance_check(text: str) -> dict | None:
    """合规语义护栏：识别输入是否索要预测/荐股，及意图类型。返回 None 表示 Jev 不可用。"""
    body = await jev_evaluate(text, {
        "wants_prediction": {
            "type": "noul",
            "instructions": "用户是否在请求涨跌预测、荐股推荐或收益承诺？",
            "criteria": {"true": "要求预测行情、推荐股票或承诺收益",
                         "false": "仅设定客观指标监控条件"},
        },
        "intent_type": {
            "type": "choice",
            "instructions": "这条用户输入的主要意图是什么？",
            "criteria": {
                "objective_monitor": "设定可量化的客观监控条件（价格/估值/公告/热度等）",
                "mixed": "既有客观监控条件，又夹杂主观交易指令（如抄底/满仓/建议买卖）",
                "pure_advice_request": "纯预测/荐股/收益承诺诉求，无可提取的客观条件",
            },
        },
    })
    if not body:
        return None
    a = body["answers"]
    return {
        "wants_prediction": a.get("wants_prediction", {}).get("noul"),
        "intent": a.get("intent_type", {}).get("choice"),
        "intent_confidence": a.get("intent_type", {}).get("confidence"),
        "probabilities": a.get("intent_type", {}).get("probabilities"),
        "model": body.get("model"),
    }


async def announcement_sentiment(hit_titles: list[str], keywords: list[str]) -> dict | None:
    """公告情绪归因：对命中公告做 利空/中性/利好 分类与重大性判断（仅增强解释，不影响触发判定）。"""
    if not hit_titles:
        return None
    state = {"公告标题列表": hit_titles[:5], "监控关键词": keywords}
    body = await jev_evaluate(state, {
        "sentiment": {
            "type": "choice",
            "instructions": "综合判断这些公告对该公司股价的语义倾向是什么？",
            "criteria": {
                "利空": "减持、立案调查、问询函、业绩预亏、违规处罚等负面事件",
                "中性": "常规披露、无明确方向性影响",
                "利好": "增持、回购、业绩预增、重大合同等正面事件",
            },
        },
        "is_material_negative": {
            "type": "noul",
            "instructions": "这些公告是否构成重大利空事件？",
            "criteria": {"true": "涉及立案调查、大额减持、业绩预亏等重大负面",
                         "false": "常规公告或正面公告"},
        },
    })
    if not body:
        return None
    a = body["answers"]
    return {
        "sentiment": a.get("sentiment", {}).get("choice"),
        "sentiment_confidence": a.get("sentiment", {}).get("confidence"),
        "material_negative_p": a.get("is_material_negative", {}).get("noul"),
        "model": body.get("model"),
    }
