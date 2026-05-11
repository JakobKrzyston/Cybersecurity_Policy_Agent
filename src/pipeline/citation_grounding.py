"""Citation Grounding: deterministic hallucination check on a ReasonerDecision."""

from src.models.decision import ReasonerDecision

_ESCALATE_DECISION = ReasonerDecision(
    action="escalate",
    tool_calls=[],
    reasoning="Citation grounding failed: one or more cited sections were not in the retrieved policy set.",
    cited_sections=[],
    user_message_draft="Your request could not be verified against policy. It has been escalated to a human agent.",
)


def check_citation_grounding(
    decision: ReasonerDecision,
    retrieved_ids: set[str],
) -> ReasonerDecision:
    """Validate that every citation in the decision is grounded in the retrieved policy chunks.

    Args:
        decision: The ReasonerDecision to validate.
        retrieved_ids: Set of chunk IDs returned by the Policy Retriever for this request.

    Returns:
        The original decision unchanged if all citations are grounded; otherwise a replacement
        escalate decision.
    """
    for section_id in decision.cited_sections:
        if section_id not in retrieved_ids:
            return _ESCALATE_DECISION

    for tool_call in decision.tool_calls:
        for section_id in tool_call.policy_basis:
            if section_id not in retrieved_ids:
                return _ESCALATE_DECISION

    return decision
