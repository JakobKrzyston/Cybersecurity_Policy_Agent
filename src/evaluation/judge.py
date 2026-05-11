"""LLM-as-judge: scores Reasoner Decisions against policy for evaluation coverage."""

import json
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from src.config.config import get_judge_model_id
from src.infra.llm import instrumented_llm_call
from src.models.decision import ReasonerDecision
from src.models.trace import Tracer
from src.pipeline.chunker import PolicyChunk


class JudgeVerdict(BaseModel):
    """Structured verdict from the LLM-as-judge evaluation."""

    verdict: Literal["pass", "fail", "uncertain"]
    confidence: float
    reasoning: str


_JUDGE_SYSTEM = (
    "You are an objective policy compliance evaluator for a cybersecurity helpdesk agent.\n"
    "Given a user request, a policy decision (action, cited sections, and user message draft), "
    "and the relevant policy sections, evaluate whether the decision is correct.\n"
    "Do NOT consider the agent's internal reasoning — evaluate only the action, cited_sections, "
    "and user_message_draft against the policy text.\n\n"
    "Respond with ONLY a JSON object:\n"
    '{"verdict": "pass" | "fail" | "uncertain", "confidence": <float 0.0-1.0>, "reasoning": "<brief explanation>"}'
)

_FALLBACK_VERDICT = JudgeVerdict(verdict="uncertain", confidence=0.0, reasoning="Judge output failed validation.")


def score(
    request: str,
    decision: ReasonerDecision,
    policy_chunks: list[PolicyChunk],
    tracer: Tracer,
    llm_call_fn: Optional[Callable] = None,
) -> JudgeVerdict:
    """Score a ReasonerDecision against policy using the judge LLM.

    Args:
        request: Original user request string.
        decision: ReasonerDecision to evaluate; the reasoning field is excluded from the prompt.
        policy_chunks: Policy chunks the Retriever returned for this request.
        tracer: Pipeline trace context; an LLM span is appended via instrumented_llm_call.
        llm_call_fn: LLM callable override; defaults to instrumented_llm_call.

    Returns:
        JudgeVerdict with verdict (pass/fail/uncertain), confidence, and reasoning.
    """
    if llm_call_fn is None:
        llm_call_fn = instrumented_llm_call

    policy_text = "\n\n".join(f"[Section {c.id}]\n{c.text}" for c in policy_chunks)
    decision_text = (
        f"Action: {decision.action}\n"
        f"Cited sections: {decision.cited_sections}\n"
        f"User message draft: {decision.user_message_draft}"
    )
    user_content = (
        f"## User Request\n{request}\n\n"
        f"## Policy Sections\n{policy_text}\n\n"
        f"## Decision\n{decision_text}"
    )

    result = llm_call_fn(
        get_judge_model_id(),
        [{"role": "user", "content": user_content}],
        tracer,
        system=_JUDGE_SYSTEM,
    )

    try:
        raw = result["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return JudgeVerdict(**data)
    except Exception:
        return _FALLBACK_VERDICT
