"""Tests for LLM-as-judge evaluation."""

import json

import pytest

from src.evaluation.judge import JudgeVerdict, score
from src.models.decision import ReasonerDecision
from src.models.trace import PipelineSpan, Tracer
from src.pipeline.chunker import PolicyChunk


def _stub_llm(verdict_dict: dict):
    """Return a stub LLM callable that always responds with verdict_dict."""
    def _fn(model_id, messages, tracer, system=None):
        content = json.dumps(verdict_dict)
        if tracer is not None:
            tracer.append_span(PipelineSpan(
                name="llm",
                inputs={"model_id": model_id, "message_count": len(messages)},
                outputs={"content": content, "input_tokens": 5, "output_tokens": 5,
                         "cached_tokens": 0, "cost": 0.0, "retries": 0},
                latency_ms=1.0,
            ))
        return {"content": content, "input_tokens": 5, "output_tokens": 5,
                "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}
    return _fn


def _decision(reasoning="Policy §1.1.a permits this action.", **kwargs) -> ReasonerDecision:
    return ReasonerDecision(
        action="allow",
        tool_calls=[],
        reasoning=reasoning,
        cited_sections=["1.1.a"],
        user_message_draft="Done.",
        **kwargs,
    )


_CHUNKS = [PolicyChunk(id="1.1.a", text="§1.1.a. Password resets are permitted.", tags=[])]


def test_score_returns_judge_verdict_with_required_fields():
    verdict_data = {"verdict": "pass", "confidence": 0.9, "reasoning": "Correct policy cited."}
    result = score("Reset my password.", _decision(), _CHUNKS, Tracer(), llm_call_fn=_stub_llm(verdict_data))

    assert isinstance(result, JudgeVerdict)
    assert result.verdict == "pass"
    assert result.confidence == pytest.approx(0.9)
    assert "Correct" in result.reasoning


def test_score_reasoning_field_not_in_judge_prompt():
    """Judge must not see the Reasoner's reasoning field — it must evaluate independently."""
    captured: list[dict] = []

    def _capturing_fn(model_id, messages, tracer, system=None):
        captured.append({"messages": messages, "system": system})
        content = json.dumps({"verdict": "pass", "confidence": 0.8, "reasoning": "OK"})
        return {"content": content, "input_tokens": 5, "output_tokens": 5,
                "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}

    decision = _decision("TOP SECRET INTERNAL REASONING DO NOT LEAK")
    score("Reset my password.", decision, _CHUNKS, Tracer(), llm_call_fn=_capturing_fn)

    assert captured, "LLM was never called"
    all_text = json.dumps(captured)
    assert "TOP SECRET INTERNAL REASONING DO NOT LEAK" not in all_text


def test_score_returns_uncertain_on_bad_llm_response():
    """Malformed judge output falls back to uncertain verdict."""
    def _bad_fn(model_id, messages, tracer, system=None):
        return {"content": "not valid json {{{", "input_tokens": 5, "output_tokens": 5,
                "cached_tokens": 0, "cost": 0.0, "retries": 0, "model_id": model_id}

    result = score("Reset my password.", _decision(), _CHUNKS, Tracer(), llm_call_fn=_bad_fn)

    assert result.verdict == "uncertain"


def test_score_all_verdicts_accepted():
    for verdict in ("pass", "fail", "uncertain"):
        result = score(
            "Request.", _decision(), _CHUNKS, Tracer(),
            llm_call_fn=_stub_llm({"verdict": verdict, "confidence": 0.5, "reasoning": "ok"}),
        )
        assert result.verdict == verdict
