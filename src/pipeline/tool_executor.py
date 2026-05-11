"""Tool Executor: validates and executes tool calls from a ReasonerDecision."""

from typing import Optional

from src.infra.store import RateLimitStore
from src.models.decision import ReasonerDecision
from src.pipeline.output_filter import filter_output

# (tool_name, max_count, window_days) — policy §1.1.b
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "reset_password": (3, 30),
}


def execute(
    decision: ReasonerDecision,
    trust_tier: str,
    risk: str,
    registry: dict,
    tracer,
    store: Optional[RateLimitStore] = None,
    identity: str = "",
) -> list[dict]:
    """Re-validate and execute tool calls from a ReasonerDecision.

    Args:
        decision: Validated ReasonerDecision from the Reasoner.
        trust_tier: Session trust tier from the Trust Gate.
        risk: Session risk classification from the Trust Gate.
        registry: Mapping of tool name to callable; injectable for testing.
        tracer: Pipeline trace context (span appended on completion).

    Returns:
        List of dicts with 'tool' and 'result' keys, one per tool call.

    Raises:
        KeyError: If a tool name is not present in the registry.
        PermissionError: If risk is 'red' and the tool is not 'escalate_to_human'.
    """
    results = []
    for tool_call in decision.tool_calls:
        if risk == "red" and tool_call.tool != "escalate_to_human":
            raise PermissionError(
                f"Red-risk session may not execute '{tool_call.tool}'; only escalate_to_human is permitted."
            )
        if store is not None and tool_call.tool in _RATE_LIMITS:
            max_count, window_days = _RATE_LIMITS[tool_call.tool]
            if store.count_recent(identity, tool_call.tool, window_days) >= max_count:
                raise PermissionError(
                    f"rate limit exceeded for '{tool_call.tool}': "
                    f"max {max_count} per {window_days} days (policy §1.1.b)."
                )
        if tool_call.tool not in registry:
            raise KeyError(f"Tool '{tool_call.tool}' is not in the registry.")
        raw = registry[tool_call.tool](**tool_call.arguments)
        filtered = filter_output(tool_call.tool, raw, tracer)
        if store is not None and tool_call.tool in _RATE_LIMITS:
            store.record_action(identity, tool_call.tool)
        results.append({"tool": tool_call.tool, "result": filtered})
    return results
