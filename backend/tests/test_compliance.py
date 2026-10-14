"""TC-08 ~ TC-09：合规边界（纯违规拦截 / 混合意图剥离 / 输出清洗）。"""
from app.services.compliance_guard import check_input, sanitize_text


def test_tc08_pure_recommendation_rejected():
    """纯荐股/预测诉求：前置拦截，不生成任务。"""
    for q in ["推荐几只明天必涨的牛股", "预测一下明天宁德时代会涨还是会跌",
              "有没有稳赚不赔的票"]:
        r = check_input(q)
        assert r["passed"] is False, q
        assert "不提供" in r["rejected_reason"]


def test_tc09_mixed_intent_stripped(client):
    """混合意图：剥离主观词，保留客观监控条件。"""
    r = check_input("当比亚迪跌破 240 元时提醒我满仓抄底")
    assert r["passed"] is True
    assert "满仓" in r["stripped_terms"] and "抄底" in r["stripped_terms"]
    # 客观条件仍可编译
    resp = client.post("/api/v1/tasks/parse-nl", json={"nl_query": "当比亚迪跌破 240 元时提醒我满仓抄底"})
    body = resp.json()
    assert body["compliance_passed"] is True
    assert body["draft_rule"] is not None
    assert "比亚迪" in body["draft_rule"]["rule_tree"]["conditions"][0]["target_name"]


def test_output_sanitizer():
    """后置输出清洗：违规词替换，绝不外泄。"""
    for w in ["建议买入", "必涨", "稳赚", "满仓"]:
        out = sanitize_text(f"这只股票{w}，值得关注")
        assert w not in out


def test_compliance_audit_and_api(client):
    """/simulator/compliance-test 演示接口可用并记录审计。"""
    r = client.post("/api/v1/simulator/compliance-test?text=" + "推荐几只明天必涨的牛股")
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["passed"] is False
