"""Citation Grounding tests: deterministic hallucination check on ReasonerDecision citations."""

import pytest

from src.models.decision import ReasonerDecision, ToolCall
from src.pipeline.citation_grounding import check_citation_grounding


def _decision(cited_sections=None, tool_calls=None, action="allow"):
    return ReasonerDecision(
        action=action,
        tool_calls=tool_calls or [],
        reasoning="some reasoning",
        cited_sections=cited_sections or [],
        user_message_draft="ok",
    )


def test_all_cited_sections_grounded_passes_decision_through():
    decision = _decision(cited_sections=["1.1.a", "2.3.b"])
    retrieved = {"1.1.a", "2.3.b", "3.0"}
    result = check_citation_grounding(decision, retrieved)
    assert result is decision


def test_ungrounded_cited_section_escalates():
    decision = _decision(cited_sections=["1.1.a", "9.9.z"])
    retrieved = {"1.1.a"}
    result = check_citation_grounding(decision, retrieved)
    assert result.action == "escalate"
    assert len(result.user_message_draft) > 0


def test_all_policy_basis_grounded_passes_decision_through():
    tool_calls = [
        ToolCall(tool="reset_password", arguments={}, policy_basis=["1.1.a", "1.1.b"]),
        ToolCall(tool="lookup_employee", arguments={}, policy_basis=["3.2.a"]),
    ]
    decision = _decision(cited_sections=[], tool_calls=tool_calls)
    retrieved = {"1.1.a", "1.1.b", "3.2.a"}
    result = check_citation_grounding(decision, retrieved)
    assert result is decision


def test_ungrounded_policy_basis_escalates():
    tool_calls = [
        ToolCall(tool="reset_password", arguments={}, policy_basis=["1.1.a", "HALLUCINATED"]),
    ]
    decision = _decision(cited_sections=[], tool_calls=tool_calls)
    retrieved = {"1.1.a"}
    result = check_citation_grounding(decision, retrieved)
    assert result.action == "escalate"
    assert len(result.user_message_draft) > 0


def test_empty_citations_passes_through():
    decision = _decision(cited_sections=[], tool_calls=[])
    result = check_citation_grounding(decision, retrieved_ids=set())
    assert result is decision
