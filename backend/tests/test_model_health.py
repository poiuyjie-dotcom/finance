"""Model health reflects validated calls, not merely configured credentials."""
import json

import httpx
import pytest

from app import config
from app.services import jev_client, nl2rule_compiler as compiler


@pytest.fixture
def model_config(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "test-secret-do-not-expose")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://model.invalid/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(compiler, "_llm_status_config", None)
    monkeypatch.setattr(compiler, "_llm_status", {})


def mock_provider(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler)))


def test_configured_does_not_mean_connected(model_config, monkeypatch):
    assert compiler.get_llm_status()["status"] == "UNKNOWN"
    assert compiler.get_llm_status()["enabled"] is True
    monkeypatch.setattr(config, "LLM_MODEL", "")
    assert compiler.get_llm_status()["enabled"] is False


@pytest.mark.asyncio
async def test_validated_call_marks_healthy_and_config_change_resets(model_config, monkeypatch):
    rule, _, _ = compiler.parse_nl_to_rule("宁德时代跌破200元")
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(rule.model_dump(mode="json"))}}]}))
    assert await compiler._llm_compile("宁德时代跌破200元") is not None
    status = compiler.get_llm_status()
    assert status["status"] == "HEALTHY" and status["last_sync"]
    assert status["latency_ms"] >= 0
    monkeypatch.setattr(config, "LLM_API_KEY", "changed-secret")
    assert compiler.get_llm_status()["status"] == "UNKNOWN"


@pytest.mark.asyncio
@pytest.mark.parametrize("code,body", [(401, {"error": "test-secret-do-not-expose"}), (200, {"choices": []})])
async def test_failed_or_invalid_call_reports_error_without_secrets(model_config, monkeypatch, code, body):
    mock_provider(monkeypatch, lambda request: httpx.Response(code, json=body))
    assert await compiler._llm_compile("宁德时代跌破200元") is None
    status = compiler.get_llm_status()
    assert status["status"] == "ERROR" and status["last_sync"]
    assert "test-secret" not in json.dumps(status)
    assert "model.invalid" not in json.dumps(status)


def test_jev_model_change_resets_status_and_cached_answers(monkeypatch):
    monkeypatch.setattr(jev_client, "_status_config", (config.JEV_API_KEY, config.JEV_MODEL))
    monkeypatch.setattr(jev_client, "_status", {"status": "HEALTHY", "last_sync": "old", "last_error": ""})
    monkeypatch.setattr(jev_client, "_cache", {"old": (0, {"answers": {}})})
    monkeypatch.setattr(config, "JEV_MODEL", "changed-model")
    assert jev_client.get_status()["status"] == "UNKNOWN"
    assert not jev_client._cache


def test_health_endpoint_exposes_model_status_without_credentials(client, model_config):
    response = client.get("/api/v1/datasources/health")
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["enabled"] and body["llm"]["model"] == "test-model"
    assert body["llm"]["status"] == "UNKNOWN"
    assert "model" in body["jev"]
    assert "test-secret" not in response.text and "model.invalid" not in response.text
