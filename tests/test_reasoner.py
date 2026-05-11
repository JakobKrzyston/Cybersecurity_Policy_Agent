"""Reasoner tests: system prompt builder, instrumented LLM call, and ReasonerDecision output."""

import json
import os
from unittest.mock import patch

import pytest

from src.models.decision import ReasonerDecision
from src.models.session import Session
from src.models.trace import Tracer
from src.pipeline.chunker import PolicyChunk
from src.pipeline.reasoner import build_system_prompt, reason
from src.infra.llm import instrumented_llm_call


# ---------------------------------------------------------------------------
# Fake Anthropic client (for instrumented_llm_call tests)
# ---------------------------------------------------------------------------

class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    cache_read_input_tokens = 2


class _FakeTextBlock:
    text = "Hello from fake LLM"


class _FakeMessage:
    usage = _FakeUsage()
    content = [_FakeTextBlock()]


class _FakeAnthropicClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            return _FakeMessage()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(chunk_id: str) -> PolicyChunk:
    return PolicyChunk(id=chunk_id, text=f"### 1 Section\n{chunk_id} clause text.", tags=["auth"])


_VALID_DECISION_JSON = json.dumps({
    "action": "deny",
    "tool_calls": [],
    "reasoning": "Not authorized under §1.1.a",
    "cited_sections": ["1.1.a"],
    "user_message_draft": "I cannot reset your password without MFA.",
})


def _fake_llm_fn(content: str = _VALID_DECISION_JSON):
    """Return a fake llm_call_fn that yields fixed content."""
    def _fn(model_id, messages, tracer, system=None):
        return {
            "content": content,
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_tokens": 0,
            "cost": 0.0,
            "retries": 0,
            "model_id": model_id,
        }
    return _fn


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

def test_build_system_prompt_contains_agent_role_persona():
    prompt = build_system_prompt(policy_chunks=[], trust_tier="verified_employee", risk="blue")
    assert "helpdesk" in prompt.lower()


def test_build_system_prompt_contains_policy_chunk_section_ids():
    chunks = [_chunk("1.1.a"), _chunk("3.2.b")]
    prompt = build_system_prompt(policy_chunks=chunks, trust_tier="verified_employee", risk="blue")
    assert "1.1.a" in prompt
    assert "3.2.b" in prompt


def test_build_system_prompt_contains_trust_tier_and_risk():
    prompt = build_system_prompt(policy_chunks=[], trust_tier="managed_device", risk="red")
    assert "managed_device" in prompt
    assert "red" in prompt


def test_build_system_prompt_contains_all_five_tool_names():
    prompt = build_system_prompt(policy_chunks=[], trust_tier="verified_employee", risk="blue")
    for tool in ["reset_password", "lookup_employee", "grant_file_access", "query_hr_database", "escalate_to_human"]:
        assert tool in prompt


def test_user_request_is_sole_content_of_user_message_turn():
    """The user turn in messages must contain only the raw request — no policy, no context."""
    captured_messages = []

    def capturing_llm(model_id, messages, tracer, system=None):
        captured_messages.extend(messages)
        return {"content": _VALID_DECISION_JSON, "input_tokens": 1, "output_tokens": 1,
                "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}

    reason(
        Session(), [], Tracer(),
        user_request="Reset my password",
        trust_tier="verified_employee", risk="blue",
        llm_call_fn=capturing_llm,
    )
    user_turns = [m for m in captured_messages if m.get("role") == "user"]
    assert len(user_turns) == 1
    assert user_turns[0]["content"] == "Reset my password"


# ---------------------------------------------------------------------------
# instrumented_llm_call
# ---------------------------------------------------------------------------

def test_instrumented_llm_call_appends_span_to_tracer():
    tracer = Tracer()
    instrumented_llm_call(
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hi"}],
        tracer,
        client=_FakeAnthropicClient(),
    )
    assert len(tracer.spans) == 1


def test_instrumented_llm_call_span_has_required_output_fields():
    tracer = Tracer()
    instrumented_llm_call(
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hi"}],
        tracer,
        client=_FakeAnthropicClient(),
    )
    span = tracer.spans[0]
    assert span.latency_ms >= 0
    for field in ("input_tokens", "output_tokens", "cached_tokens", "cost", "retries"):
        assert field in span.outputs, f"missing span output field: {field}"


def test_instrumented_llm_call_cost_computed_from_model_prices():
    tracer = Tracer()
    # _FakeUsage: input=10, output=5; model_prices.json: 0.000003 input, 0.000015 output
    result = instrumented_llm_call(
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hi"}],
        tracer,
        client=_FakeAnthropicClient(),
    )
    expected = 10 * 0.000003 + 5 * 0.000015
    assert abs(result["cost"] - expected) < 1e-12


def test_instrumented_llm_call_returns_content_string():
    tracer = Tracer()
    result = instrumented_llm_call(
        "claude-sonnet-4-6",
        [{"role": "user", "content": "hi"}],
        tracer,
        client=_FakeAnthropicClient(),
    )
    assert result["content"] == "Hello from fake LLM"


# ---------------------------------------------------------------------------
# reason() end-to-end
# ---------------------------------------------------------------------------

def test_reason_with_valid_json_returns_reasoner_decision():
    decision = reason(
        Session(), [], Tracer(),
        user_request="Reset my password",
        trust_tier="verified_employee", risk="blue",
        llm_call_fn=_fake_llm_fn(_VALID_DECISION_JSON),
    )
    assert isinstance(decision, ReasonerDecision)
    assert decision.action == "deny"
    assert decision.cited_sections == ["1.1.a"]


def test_reason_with_invalid_json_returns_escalate_decision():
    decision = reason(
        Session(), [], Tracer(),
        user_request="Do something",
        trust_tier="verified_employee", risk="blue",
        llm_call_fn=_fake_llm_fn("not valid json at all {{"),
    )
    assert decision.action == "escalate"
    assert len(decision.user_message_draft) > 0


def test_reason_with_wrong_schema_returns_escalate_decision():
    # Valid JSON but missing required ReasonerDecision fields → Pydantic error → escalate
    partial = json.dumps({"action": "allow"})
    decision = reason(
        Session(), [], Tracer(),
        user_request="Do something",
        trust_tier="verified_employee", risk="blue",
        llm_call_fn=_fake_llm_fn(partial),
    )
    assert decision.action == "escalate"


def test_reason_uses_model_id_from_config_env():
    captured = []

    def capturing_llm(model_id, messages, tracer, system=None):
        captured.append(model_id)
        return {"content": _VALID_DECISION_JSON, "input_tokens": 1, "output_tokens": 1,
                "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}

    with patch.dict(os.environ, {"REASONER_MODEL_ID": "claude-haiku-4-5-20251001"}):
        reason(
            Session(), [], Tracer(),
            user_request="test",
            trust_tier="verified_employee", risk="blue",
            llm_call_fn=capturing_llm,
        )

    assert captured[0] == "claude-haiku-4-5-20251001"
