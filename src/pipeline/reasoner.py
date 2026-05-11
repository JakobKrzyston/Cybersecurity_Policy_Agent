"""Reasoner: instrumented LLM call that produces a ReasonerDecision as structured JSON."""

import json
from typing import Callable, Optional

from src.config.config import get_reasoner_model_id
from src.infra.llm import instrumented_llm_call
from src.models.decision import ReasonerDecision
from src.models.session import Session
from src.models.trace import Tracer
from src.pipeline.chunker import PolicyChunk

_TOOL_REGISTRY = [
    "reset_password",
    "lookup_employee",
    "grant_file_access",
    "query_hr_database",
    "escalate_to_human",
]

_AGENT_ROLE = (
    "You are a cybersecurity policy agent for the Gaggia Helpdesk. "
    "Your role is to evaluate employee requests against company security policy "
    "and produce a structured JSON decision. You must cite policy section IDs to support every decision."
)

_ESCALATE_DECISION = ReasonerDecision(
    action="escalate",
    tool_calls=[],
    reasoning="Reasoner output failed validation.",
    cited_sections=[],
    user_message_draft="Your request could not be processed automatically. It has been escalated to a human agent.",
)


def build_system_prompt(
    policy_chunks: list[PolicyChunk],
    trust_tier: str,
    risk: str,
) -> str:
    """Build the per-request system prompt for the Reasoner.

    Args:
        policy_chunks: Policy chunks retrieved for this request (from the Policy Retriever).
        trust_tier: Session trust tier from the Trust Gate (e.g., 'managed_device').
        risk: Session risk classification from the Trust Gate (e.g., 'red', 'blue').

    Returns:
        System prompt string including agent role, policy chunks with section IDs,
        session trust context, tool registry, and response format instructions.
    """
    chunks_text = (
        "\n\n".join(f"[Section {c.id}]\n{c.text}" for c in policy_chunks)
        if policy_chunks
        else "(No specific policy sections retrieved for this query.)"
    )
    tools_text = "\n".join(f"- {tool}" for tool in _TOOL_REGISTRY)

    return f"""{_AGENT_ROLE}

## Session Context
Trust tier: {trust_tier}
Risk classification: {risk}

## Retrieved Policy Sections
{chunks_text}

## Available Tools
{tools_text}

## Response Format
Respond with ONLY a JSON object matching this exact schema — no other text:
{{
  "action": "allow" | "deny" | "escalate" | "clarify",
  "tool_calls": [{{"tool": "<name>", "arguments": {{}}, "policy_basis": ["<section_id>"]}}],
  "reasoning": "<explanation citing policy section IDs>",
  "cited_sections": ["<section_id>", ...],
  "user_message_draft": "<message to send to the user>"
}}"""


def reason(
    session: Session,
    policy_chunks: list[PolicyChunk],
    tracer: Tracer,
    user_request: str,
    trust_tier: str,
    risk: str,
    llm_call_fn: Optional[Callable] = None,
) -> ReasonerDecision:
    """Run the Reasoner: build system prompt, call LLM, validate and return a ReasonerDecision.

    Args:
        session: In-memory session accumulating request history.
        policy_chunks: Policy chunks retrieved for this request.
        tracer: Pipeline trace context; LLM span appended by instrumented_llm_call.
        user_request: Raw request text from the user (sole content of the user turn).
        trust_tier: Session trust tier from the Trust Gate.
        risk: Session risk classification from the Trust Gate.
        llm_call_fn: Callable with signature (model_id, messages, tracer, system) -> dict;
            defaults to instrumented_llm_call.

    Returns:
        Validated ReasonerDecision. Returns an escalate decision on JSON parse or schema error.
    """
    if llm_call_fn is None:
        llm_call_fn = instrumented_llm_call

    model_id = get_reasoner_model_id()
    system_prompt = build_system_prompt(policy_chunks, trust_tier, risk)
    messages = [{"role": "user", "content": user_request}]

    result = llm_call_fn(model_id, messages, tracer, system=system_prompt)

    try:
        data = json.loads(result["content"])
        return ReasonerDecision(**data)
    except Exception:
        return _ESCALATE_DECISION
