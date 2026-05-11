"""Tests for Pydantic models: ToolCall, ReasonerDecision, Tracer, Session."""

import os
import pytest
from pydantic import ValidationError
from src.models.decision import ToolCall, ReasonerDecision
from src.models.trace import PipelineSpan, Tracer
from src.config.config import load_model_prices, get_reasoner_model_id, get_judge_model_id


def test_tool_call_validates_well_formed_entry():
    tc = ToolCall(
        tool="reset_password",
        arguments={"account_id": "u42"},
        policy_basis=["1.1.b", "15.2"],
    )
    assert tc.tool == "reset_password"
    assert tc.arguments == {"account_id": "u42"}
    assert tc.policy_basis == ["1.1.b", "15.2"]


def test_reasoner_decision_validates_all_fields():
    tc = ToolCall(tool="reset_password", arguments={"account_id": "u42"}, policy_basis=["1.1.b"])
    decision = ReasonerDecision(
        action="allow",
        tool_calls=[tc],
        reasoning="Employee is verified.",
        cited_sections=["1.1.b", "15.2"],
        user_message_draft="Your password has been reset.",
    )
    assert decision.action == "allow"
    assert len(decision.tool_calls) == 1
    assert decision.cited_sections == ["1.1.b", "15.2"]


def test_tracer_append_span_accumulates_spans():
    tracer = Tracer()
    span1 = PipelineSpan(name="trust_gate", inputs={"user": "alice"}, outputs={"tier": "verified_employee"}, latency_ms=5.0)
    span2 = PipelineSpan(name="reasoner", inputs={"query": "reset"}, outputs={"action": "allow"}, latency_ms=120.0)
    tracer.append_span(span1)
    tracer.append_span(span2)
    assert len(tracer.spans) == 2
    assert tracer.spans[0].name == "trust_gate"
    assert tracer.spans[1].name == "reasoner"


def test_config_loads_model_prices_without_error():
    prices = load_model_prices()
    assert isinstance(prices, dict)
    assert len(prices) >= 1


def test_config_reads_model_ids_from_environment(monkeypatch):
    monkeypatch.setenv("REASONER_MODEL_ID", "claude-sonnet-4-6")
    monkeypatch.setenv("JUDGE_MODEL_ID", "claude-haiku-4-5-20251001")
    assert get_reasoner_model_id() == "claude-sonnet-4-6"
    assert get_judge_model_id() == "claude-haiku-4-5-20251001"


def test_all_stub_modules_import_without_error():
    import src.pipeline.trust_gate
    import src.pipeline.policy_retriever
    import src.pipeline.reasoner
    import src.pipeline.tool_executor
    import src.pipeline.output_filter
    import src.tools.reset_password
    import src.tools.lookup_employee
    import src.tools.grant_file_access
    import src.tools.query_hr_database
    import src.tools.escalate_to_human
    import src.infra.llm
    import src.infra.store
    import src.infra.embeddings
    import src.evaluation.judge
    import src.evaluation.runner
    import src.models.session


def test_reasoner_decision_rejects_invalid_action():
    with pytest.raises(ValidationError):
        ReasonerDecision(
            action="approve",
            tool_calls=[],
            reasoning="...",
            cited_sections=[],
            user_message_draft="",
        )
