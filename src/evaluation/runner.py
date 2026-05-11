"""Evaluation runner: executes the golden test set and LLM-as-judge against the pipeline."""

import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

import yaml

from src.evaluation.judge import score as judge_score
from src.infra.llm import instrumented_llm_call
from src.infra.store import InMemoryRateLimitStore
from src.models.session import Session, SessionContext
from src.models.trace import Tracer
from src.pipeline.chunker import PolicyChunk
from src.pipeline.pipeline import Pipeline
from src.pipeline.policy_retriever import PolicyRetrieverBase
from src.pipeline.trust_gate import InMemoryBlocklist
from src.tools.escalate_to_human import escalate_to_human
from src.tools.grant_file_access import grant_file_access
from src.tools.lookup_employee import lookup_employee
from src.tools.query_hr_database import query_hr_database
from src.tools.reset_password import reset_password


_REGISTRY = {
    "reset_password": reset_password,
    "lookup_employee": lookup_employee,
    "grant_file_access": grant_file_access,
    "query_hr_database": query_hr_database,
    "escalate_to_human": escalate_to_human,
}


class _FixedRetriever(PolicyRetrieverBase):
    """Returns a fixed list of chunks regardless of query."""

    def __init__(self, chunks: list[PolicyChunk]) -> None:
        self._chunks = chunks

    def retrieve(self, query: str, tags=None, top_k: int = 5) -> list[PolicyChunk]:
        """Return the fixed chunk list."""
        return self._chunks


def _run_scenario(scenario: dict, llm_call_fn: Callable, log_path: str) -> dict:
    os.environ["PIPELINE_LOG"] = log_path

    chunks = [
        PolicyChunk(id=c["id"], text=c["text"], tags=c.get("tags", []))
        for c in scenario.get("policy_chunks", [])
    ]

    store = InMemoryRateLimitStore()
    identity = scenario.get("identity", "unknown")
    for _ in range(scenario.get("store_resets", 0)):
        store.record_action(identity, "reset_password")

    pipeline = Pipeline(
        blocklist=InMemoryBlocklist(blocked=set(scenario.get("blocked", []))),
        retriever=_FixedRetriever(chunks),
        registry=_REGISTRY,
        store=store,
        llm_call_fn=llm_call_fn,
    )

    ctx = SessionContext(
        identity=identity,
        sso_age_hours=float(scenario.get("sso_age_hours", 1.0)),
        mfa_age_hours=float(scenario.get("mfa_age_hours", 0.5)),
        device_type=scenario.get("device_type", "managed"),
    )

    tracer = Tracer()
    result = pipeline.run(scenario["request"], Session(), ctx, tracer)

    verdict = judge_score(
        request=scenario["request"],
        decision=result.decision,
        policy_chunks=chunks,
        tracer=tracer,
        llm_call_fn=llm_call_fn,
    )

    return {
        "id": scenario["id"],
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "reasoning": verdict.reasoning,
        "action": result.decision.action,
    }


def run_golden_suite(cases_path: str, llm_call_fn: Optional[Callable] = None) -> dict:
    """Run all YAML scenarios from cases_path through the pipeline and LLM-as-judge.

    Args:
        cases_path: Directory containing YAML scenario files (*.yaml).
        llm_call_fn: LLM call override; defaults to instrumented_llm_call for real API calls.

    Returns:
        Dict with keys: total, pass, fail, uncertain (counts), and scenarios (per-scenario details).
    """
    if llm_call_fn is None:
        llm_call_fn = instrumented_llm_call

    log_path = tempfile.mktemp(suffix=".log")
    yaml_files = sorted(Path(cases_path).glob("*.yaml"))

    report: dict = {"total": 0, "pass": 0, "fail": 0, "uncertain": 0, "scenarios": []}

    for path in yaml_files:
        with path.open() as f:
            scenario = yaml.safe_load(f)
        detail = _run_scenario(scenario, llm_call_fn, log_path)
        report["total"] += 1
        report[detail["verdict"]] += 1
        report["scenarios"].append(detail)

    return report


def _print_summary(report: dict) -> None:
    total = report["total"]
    print(f"\nEvaluation Report — {total} scenario(s)")
    print(f"  pass:      {report['pass']}")
    print(f"  fail:      {report['fail']}")
    print(f"  uncertain: {report['uncertain']}")
    print("\nPer-scenario details:")
    for s in report["scenarios"]:
        print(f"  [{s['verdict'].upper():9s}] {s['id']}  (confidence={s['confidence']:.2f})")
        if s["verdict"] != "pass":
            print(f"             {s['reasoning']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the LLM-as-judge evaluation suite.")
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).parent / "golden_cases"),
        help="Directory containing YAML scenario files.",
    )
    args = parser.parse_args()

    report = run_golden_suite(args.cases)
    print(json.dumps(report, indent=2))
    _print_summary(report)
