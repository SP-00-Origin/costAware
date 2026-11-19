"""Phase 5: verdict parsing, observation isolation, provider failures and usage."""
import json
import sys
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.verifier.verifier import parse_verdict, verify_step, ScriptedVerifier
from src.agent.llm import make_verifier_llm


class ReplyModel:
    def __init__(self, content):
        self.content = content
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.content,
                         usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18})


@pytest.mark.parametrize("content", [
    '{"suspicious": false, "reason": "Consistent."}',
    '```json\n{"suspicious": false, "reason": "Consistent."}\n```',
    [{"type": "text", "text": '{"suspicious": false, "reason": "Consistent."}'}],
])
def test_valid_verdict_formats(content):
    assert parse_verdict(content) == {"suspicious": False, "reason": "Consistent."}


@pytest.mark.parametrize("content", [None, "", "null", "[]", "{}", "not json",
    '{"suspicious": "false", "reason": "x"}', '{"suspicious": 0, "reason": "x"}',
    '{"suspicious": false}', '{"suspicious": true, "reason": " "}',
    '{"suspicious": true, "reason": null}'])
def test_invalid_verdict_rejected(content):
    with pytest.raises((ValueError, TypeError)):
        parse_verdict(content)


def test_only_observed_evidence_enters_verifier_and_usage_is_recorded():
    model = ReplyModel('{"suspicious": true, "reason": "Budget conflicts."}')
    record = {"tool": "check_budget", "args": {"budget_id": "B"},
              "observed_result": {"remaining": 8}, "true_result": {"secret": "HIDDEN"},
              "fault_injected": "SECRET_FAULT", "oracle_pass": "SECRET_ORACLE"}
    result = verify_step(model, "Buy parts", {"tool": "check_budget", "args": {},
                                            "true_state": "SECRET_STATE"}, {"remaining": 9}, [record])
    content = model.messages[-1].content
    assert all(secret not in content for secret in ["HIDDEN", "SECRET_FAULT", "SECRET_ORACLE", "SECRET_STATE"])
    assert json.loads(content)["history"] == [{"tool": "check_budget", "args": {"budget_id": "B"},
                                             "observed_result": {"remaining": 8}}]
    assert result["verdict"]["suspicious"] and result["error"] is None
    assert result["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert result["latency_ms"] >= 0


def test_malformed_reply_keeps_billed_tokens_and_reports_failure():
    result = verify_step(ReplyModel("invalid"), "goal", {"tool": "x", "args": {}}, {}, [])
    assert result["verdict"]["suspicious"] and result["error"]
    assert result["usage"]["input_tokens"] == 11


def test_provider_failure_is_not_a_successful_verdict():
    class BrokenModel:
        def invoke(self, messages):
            raise ConnectionError("offline")
    result = verify_step(BrokenModel(), "goal", {"tool": "x", "args": {}}, {}, [])
    assert result["verdict"]["suspicious"] and result["error"] == "ConnectionError: offline"


@pytest.mark.parametrize("provider,key", [("groq", "GROQ_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_real_verifier_requires_key(provider, key, monkeypatch):
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match=key):
        make_verifier_llm(provider)


def test_scripted_verifier_is_available_without_a_task_or_key():
    assert isinstance(make_verifier_llm("scripted"), ScriptedVerifier)


@pytest.mark.parametrize("provider,module,name,key", [
    ("groq", "langchain_groq", "ChatGroq", "GROQ_API_KEY"),
    ("anthropic", "langchain_anthropic", "ChatAnthropic", "ANTHROPIC_API_KEY"),
])
def test_provider_verifier_has_no_action_tools(provider, module, name, key, monkeypatch):
    class ProviderModel:
        def __init__(self, **kwargs):
            self.config = kwargs
        def bind_tools(self, *args, **kwargs):
            pytest.fail("Verifier must not have executable agent tools")
    monkeypatch.setenv(key, "test-placeholder")
    monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{name: ProviderModel}))
    model = make_verifier_llm(provider, model="test-model")
    assert model.config["model"] == "test-model" and model.config["temperature"] == 0


def test_groq_gpt_oss_verifier_requests_json_without_tools(monkeypatch):
    class ProviderModel:
        def __init__(self, **kwargs):
            self.config = kwargs

        def bind(self, **kwargs):
            self.request = kwargs
            return self

    monkeypatch.setenv("GROQ_API_KEY", "test-placeholder")
    monkeypatch.setitem(sys.modules, "langchain_groq", SimpleNamespace(ChatGroq=ProviderModel))
    model = make_verifier_llm("groq", model="openai/gpt-oss-20b")
    assert model.request == {"response_format": {"type": "json_object"}}
    assert model.config["max_tokens"] == 2048
