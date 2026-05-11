"""Tool Executor tests: validates and executes tool calls from a ReasonerDecision."""

import pytest

from src.infra.store import InMemoryRateLimitStore
from src.models.decision import ReasonerDecision, ToolCall
from src.pipeline.tool_executor import execute


def _decision(tool_calls: list[ToolCall], action: str = "allow") -> ReasonerDecision:
    return ReasonerDecision(
        action=action,
        tool_calls=tool_calls,
        reasoning="policy allows this",
        cited_sections=["1.1.a"],
        user_message_draft="Done.",
    )


def _tool_call(tool: str, arguments: dict) -> ToolCall:
    return ToolCall(tool=tool, arguments=arguments, policy_basis=["1.1.a"])


def test_registered_tool_is_executed():
    registry = {"reset_password": lambda account_id: {"status": "reset", "account_id": account_id}}
    decision = _decision([_tool_call("reset_password", {"account_id": "alice"})])
    results = execute(decision, trust_tier="managed_device", risk="blue", registry=registry, tracer=None)
    assert results[0]["tool"] == "reset_password"
    assert results[0]["result"]["status"] == "reset"
    assert results[0]["result"]["account_id"] == "alice"


def test_unregistered_tool_raises():
    registry = {}
    decision = _decision([_tool_call("delete_all_data", {"confirm": True})])
    with pytest.raises(KeyError, match="delete_all_data"):
        execute(decision, trust_tier="managed_device", risk="blue", registry=registry, tracer=None)


def test_red_risk_blocks_non_escalate_tool():
    registry = {"reset_password": lambda account_id: {"status": "reset", "account_id": account_id}}
    decision = _decision([_tool_call("reset_password", {"account_id": "alice"})])
    with pytest.raises(PermissionError, match="reset_password"):
        execute(decision, trust_tier="managed_device", risk="red", registry=registry, tracer=None)


def test_red_risk_allows_escalate_to_human():
    registry = {"escalate_to_human": lambda reason, session_id: {"status": "escalated", "ticket_id": "T-001"}}
    decision = _decision([_tool_call("escalate_to_human", {"reason": "flagged", "session_id": "s1"})])
    results = execute(decision, trust_tier="managed_device", risk="red", registry=registry, tracer=None)
    assert results[0]["tool"] == "escalate_to_human"
    assert results[0]["result"]["status"] == "escalated"


def test_multiple_tool_calls_all_execute():
    registry = {
        "lookup_employee": lambda employee_id: {"employee_id": employee_id, "name": "Alice"},
        "grant_file_access": lambda employee_id, resource: {"status": "granted", "resource": resource},
    }
    decision = _decision([
        _tool_call("lookup_employee", {"employee_id": "alice"}),
        _tool_call("grant_file_access", {"employee_id": "alice", "resource": "/reports"}),
    ])
    results = execute(decision, trust_tier="managed_device", risk="blue", registry=registry, tracer=None)
    assert len(results) == 2
    assert results[0]["tool"] == "lookup_employee"
    assert results[1]["tool"] == "grant_file_access"
    assert results[1]["result"]["resource"] == "/reports"


def test_empty_tool_calls_returns_empty_list():
    decision = _decision([])
    results = execute(decision, trust_tier="managed_device", risk="blue", registry={}, tracer=None)
    assert results == []


def test_reset_password_blocked_when_rate_limit_reached():
    store = InMemoryRateLimitStore()
    for _ in range(3):
        store.record_action("alice", "reset_password")
    registry = {"reset_password": lambda account_id: {"status": "reset", "account_id": account_id}}
    decision = _decision([_tool_call("reset_password", {"account_id": "alice"})])
    with pytest.raises(PermissionError, match="rate limit"):
        execute(decision, trust_tier="managed_device", risk="blue",
                registry=registry, tracer=None, store=store, identity="alice")


def test_reset_password_allowed_below_rate_limit():
    store = InMemoryRateLimitStore()
    for _ in range(2):
        store.record_action("alice", "reset_password")
    registry = {"reset_password": lambda account_id: {"status": "reset", "account_id": account_id}}
    decision = _decision([_tool_call("reset_password", {"account_id": "alice"})])
    results = execute(decision, trust_tier="managed_device", risk="blue",
                      registry=registry, tracer=None, store=store, identity="alice")
    assert results[0]["result"]["status"] == "reset"


def test_reset_password_records_action_after_execution():
    store = InMemoryRateLimitStore()
    registry = {"reset_password": lambda account_id: {"status": "reset", "account_id": account_id}}
    decision = _decision([_tool_call("reset_password", {"account_id": "alice"})])
    execute(decision, trust_tier="managed_device", risk="blue",
            registry=registry, tracer=None, store=store, identity="alice")
    assert store.count_recent("alice", "reset_password", window_days=30) == 1
