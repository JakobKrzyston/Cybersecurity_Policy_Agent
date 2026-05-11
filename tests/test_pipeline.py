"""Pipeline integration tests: full component wiring and trace behavior."""

import json
import os

import pytest

from src.models.decision import ReasonerDecision, ToolCall
from src.models.session import Session, SessionContext
from src.models.trace import Tracer
from src.pipeline.policy_retriever import PolicyRetrieverBase
from src.pipeline.chunker import PolicyChunk
from src.pipeline.trust_gate import InMemoryBlocklist


# --- Shared fixtures ---

_CHUNK = PolicyChunk(id="1.1.a", text="1.1.a Users may reset their own password.", tags=["password"])

_ALLOW_DECISION = {
    "action": "allow",
    "tool_calls": [],
    "reasoning": "Policy 1.1.a permits this.",
    "cited_sections": ["1.1.a"],
    "user_message_draft": "Done.",
}

_ALLOW_WITH_TOOL_DECISION = {
    "action": "allow",
    "tool_calls": [{"tool": "reset_password", "arguments": {"account_id": "alice"}, "policy_basis": ["1.1.a"]}],
    "reasoning": "Policy 1.1.a permits this.",
    "cited_sections": ["1.1.a"],
    "user_message_draft": "Password reset.",
}

_UNGROUNDED_DECISION = {
    "action": "allow",
    "tool_calls": [],
    "reasoning": "Citing made-up section.",
    "cited_sections": ["99.99"],
    "user_message_draft": "Done.",
}


class _MockRetriever(PolicyRetrieverBase):
    def retrieve(self, query: str, tags=None, top_k: int = 5) -> list[PolicyChunk]:
        return [_CHUNK]


def _llm_fn(decision_dict: dict):
    """Return a llm_call_fn stub that echoes a fixed decision."""
    def _fn(model_id, messages, tracer, system=None):
        from src.models.trace import PipelineSpan
        import time
        if tracer is not None:
            tracer.append_span(PipelineSpan(
                name="llm",
                inputs={"model_id": model_id, "message_count": len(messages)},
                outputs={"content": json.dumps(decision_dict), "input_tokens": 10,
                         "output_tokens": 5, "cached_tokens": 0, "cost": 0.0, "retries": 0},
                latency_ms=1.0,
            ))
        return {"content": json.dumps(decision_dict), "input_tokens": 10,
                "output_tokens": 5, "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}
    return _fn


def _make_pipeline(decision_dict=None, blocked=None, registry=None):
    from src.pipeline.pipeline import Pipeline
    return Pipeline(
        blocklist=InMemoryBlocklist(blocked=blocked or set()),
        retriever=_MockRetriever(),
        registry=registry or {},
        llm_call_fn=_llm_fn(decision_dict or _ALLOW_DECISION),
    )


def _ctx(identity: str = "alice") -> SessionContext:
    return SessionContext(identity=identity, sso_age_hours=1.0, mfa_age_hours=0.5, device_type="managed")


# --- Test 1: tracer bullet — happy path returns PipelineResult shape ---

def test_pipeline_run_returns_pipeline_result():
    from src.pipeline.pipeline import PipelineResult
    pipeline = _make_pipeline()
    result = pipeline.run("Reset my password", Session(), _ctx(), Tracer())
    assert isinstance(result, PipelineResult)
    assert isinstance(result.decision, ReasonerDecision)
    assert isinstance(result.tool_results, list)
    assert result.trust_tier in ("anonymous", "verified_employee", "managed_device", "delegated", "verified_manager")
    assert result.risk in ("red", "grey", "blue")


# --- Test 2: trust_gate span present ---

def test_pipeline_tracer_has_trust_gate_span():
    pipeline = _make_pipeline()
    tracer = Tracer()
    pipeline.run("Reset my password", Session(), _ctx(), tracer)
    span_names = [s.name for s in tracer.spans]
    assert "trust_gate" in span_names


# --- Test 3: policy_retriever span present ---

def test_pipeline_tracer_has_policy_retriever_span():
    pipeline = _make_pipeline()
    tracer = Tracer()
    pipeline.run("Reset my password", Session(), _ctx(), tracer)
    span_names = [s.name for s in tracer.spans]
    assert "policy_retriever" in span_names


# --- Test 4: llm span present ---

def test_pipeline_tracer_has_llm_span():
    pipeline = _make_pipeline()
    tracer = Tracer()
    pipeline.run("Reset my password", Session(), _ctx(), tracer)
    span_names = [s.name for s in tracer.spans]
    assert "llm" in span_names


# --- Test 5: citation grounding blocks ungrounded citation ---

def test_pipeline_citation_grounding_escalates_on_ungrounded_citation():
    pipeline = _make_pipeline(decision_dict=_UNGROUNDED_DECISION)
    result = pipeline.run("Do something", Session(), _ctx(), Tracer())
    assert result.decision.action == "escalate"
    assert result.tool_results == []


# --- Test 6: red-risk session ---

def test_pipeline_red_risk_identity_sets_risk():
    pipeline = _make_pipeline(blocked={"mallory"})
    result = pipeline.run("Reset my password", Session(), _ctx(identity="mallory"), Tracer())
    assert result.risk == "red"


# --- Test 7: no tool calls returns empty tool_results ---

def test_pipeline_no_tool_calls_returns_empty_results():
    pipeline = _make_pipeline(decision_dict=_ALLOW_DECISION)
    result = pipeline.run("Reset my password", Session(), _ctx(), Tracer())
    assert result.tool_results == []


# --- Test 8: trace written to pipeline.log ---

def test_pipeline_writes_trace_to_log(tmp_path, monkeypatch):
    log_path = tmp_path / "pipeline.log"
    monkeypatch.setenv("PIPELINE_LOG", str(log_path))
    pipeline = _make_pipeline()
    pipeline.run("Reset my password", Session(), _ctx(), Tracer())
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert "spans" in entry
