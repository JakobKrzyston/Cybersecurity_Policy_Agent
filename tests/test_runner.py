"""Tests for the evaluation runner."""

import json
from pathlib import Path

import pytest

from src.config.config import load_model_prices
from src.evaluation.runner import run_golden_suite
from src.models.trace import PipelineSpan


def _compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    prices = load_model_prices()
    p = prices.get(model_id, {"input_price_per_token": 0.0, "output_price_per_token": 0.0})
    return input_tokens * p["input_price_per_token"] + output_tokens * p["output_price_per_token"]


def _stub_llm(decision_dict: dict, judge_verdict: dict):
    """Return a stub LLM that serves a Reasoner decision first, then a judge verdict."""
    calls: list[int] = [0]

    def _fn(model_id, messages, tracer, system=None):
        call_idx = calls[0]
        calls[0] += 1
        if call_idx == 0:
            content = json.dumps(decision_dict)
        else:
            content = json.dumps(judge_verdict)
        cost = _compute_cost(model_id, 5, 5)
        if tracer is not None:
            tracer.append_span(PipelineSpan(
                name="llm",
                inputs={"model_id": model_id, "message_count": len(messages)},
                outputs={"content": content, "input_tokens": 5, "output_tokens": 5,
                         "cached_tokens": 0, "cost": cost, "retries": 0},
                latency_ms=1.0,
            ))
        return {"content": content, "input_tokens": 5, "output_tokens": 5,
                "cached_tokens": 0, "cost": cost, "retries": 0, "model_id": model_id}
    return _fn


_DECISION = {
    "action": "allow",
    "tool_calls": [],
    "reasoning": "§1.1.a permits this.",
    "cited_sections": ["1.1.a"],
    "user_message_draft": "Done.",
}
_VERDICT = {"verdict": "pass", "confidence": 0.9, "reasoning": "Correct."}

_SCENARIO_YAML = """\
id: test_scenario
request: "Reset my password."
identity: alice
sso_age_hours: 1.0
mfa_age_hours: 0.5
device_type: managed
blocked: []
store_resets: 0
policy_chunks:
  - id: "1.1.a"
    text: "§1.1.a. Password resets are permitted."
    tags: []
"""


def _write_scenario(tmp_path: Path, content: str, name: str = "scenario.yaml") -> str:
    f = tmp_path / name
    f.write_text(content)
    return str(tmp_path)


def test_run_golden_suite_returns_summary_with_counts(tmp_path):
    cases_path = _write_scenario(tmp_path, _SCENARIO_YAML)
    stub = _stub_llm(_DECISION, _VERDICT)

    report = run_golden_suite(cases_path, llm_call_fn=stub)

    assert report["total"] == 1
    assert report["pass"] == 1
    assert report["fail"] == 0
    assert report["uncertain"] == 0


def test_run_golden_suite_includes_per_scenario_details(tmp_path):
    cases_path = _write_scenario(tmp_path, _SCENARIO_YAML)
    stub = _stub_llm(_DECISION, _VERDICT)

    report = run_golden_suite(cases_path, llm_call_fn=stub)

    assert len(report["scenarios"]) == 1
    scenario = report["scenarios"][0]
    assert scenario["id"] == "test_scenario"
    assert scenario["verdict"] == "pass"
    assert "confidence" in scenario


def test_run_golden_suite_empty_directory_returns_zero_counts(tmp_path):
    report = run_golden_suite(str(tmp_path), llm_call_fn=_stub_llm(_DECISION, _VERDICT))

    assert report["total"] == 0
    assert report["pass"] == 0
    assert report["fail"] == 0
    assert report["uncertain"] == 0
    assert report["scenarios"] == []


def test_runner_cli_exits_zero_on_empty_cases(tmp_path):
    """CLI entry point exits 0 when the cases directory is empty (no LLM calls needed)."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "src.evaluation.runner", "--cases", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd="/Users/jay/Documents/Cybersecurity_Policy_Agent",
    )
    assert result.returncode == 0
    assert '"total": 0' in result.stdout


def test_run_golden_suite_multiple_scenarios(tmp_path):
    fail_verdict = {"verdict": "fail", "confidence": 0.8, "reasoning": "Wrong action."}
    # First call → decision 1, second call → verdict 1, third call → decision 2, fourth → verdict 2
    responses = [
        json.dumps(_DECISION), json.dumps(_VERDICT),
        json.dumps(_DECISION), json.dumps(fail_verdict),
    ]
    idx: list[int] = [0]

    def _multi_fn(model_id, messages, tracer, system=None):
        content = responses[idx[0]]
        idx[0] += 1
        cost = _compute_cost(model_id, 5, 5)
        return {"content": content, "input_tokens": 5, "output_tokens": 5,
                "cached_tokens": 0, "cost": cost, "retries": 0, "model_id": model_id}

    _write_scenario(tmp_path, _SCENARIO_YAML, "s1.yaml")
    _write_scenario(tmp_path, _SCENARIO_YAML.replace("test_scenario", "test_scenario_2"), "s2.yaml")

    report = run_golden_suite(str(tmp_path), llm_call_fn=_multi_fn)

    assert report["total"] == 2
    assert report["pass"] == 1
    assert report["fail"] == 1
