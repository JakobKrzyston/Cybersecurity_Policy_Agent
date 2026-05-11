"""REPL tests: process_request helper behavior."""

import json
import io

from src.models.decision import ReasonerDecision
from src.models.session import Session, SessionContext
from src.models.trace import PipelineSpan, Tracer
from src.pipeline.chunker import PolicyChunk
from src.pipeline.policy_retriever import PolicyRetrieverBase
from src.pipeline.trust_gate import InMemoryBlocklist


_CHUNK = PolicyChunk(id="1.1.a", text="1.1.a Users may reset their own password.", tags=["password"])

_ALLOW_DECISION = {
    "action": "allow",
    "tool_calls": [],
    "reasoning": "Policy 1.1.a permits this.",
    "cited_sections": ["1.1.a"],
    "user_message_draft": "Your request is approved.",
}


class _MockRetriever(PolicyRetrieverBase):
    def retrieve(self, query: str, tags=None, top_k: int = 5) -> list[PolicyChunk]:
        return [_CHUNK]


def _llm_fn(decision_dict: dict):
    def _fn(model_id, messages, tracer, system=None):
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


def _make_pipeline():
    from src.pipeline.pipeline import Pipeline
    return Pipeline(
        blocklist=InMemoryBlocklist(blocked=set()),
        retriever=_MockRetriever(),
        registry={},
        llm_call_fn=_llm_fn(_ALLOW_DECISION),
    )


def _ctx() -> SessionContext:
    return SessionContext(identity="alice", sso_age_hours=1.0, mfa_age_hours=0.5, device_type="managed")


# --- Test 9: session accumulates request_history across calls ---

def test_process_request_accumulates_session_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LOG", str(tmp_path / "pipeline.log"))
    from src.repl import process_request
    session = Session()
    ctx = _ctx()
    pipeline = _make_pipeline()
    process_request("Turn one", session, ctx, pipeline)
    process_request("Turn two", session, ctx, pipeline)
    assert len(session.request_history) == 2


# --- Test 10: process_request returns user_message_draft ---

def test_process_request_returns_user_message_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LOG", str(tmp_path / "pipeline.log"))
    from src.repl import process_request
    session = Session()
    pipeline = _make_pipeline()
    reply = process_request("Reset my password", session, _ctx(), pipeline)
    assert reply == "Your request is approved."
