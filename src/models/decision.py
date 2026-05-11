"""Pydantic schemas for Reasoner Decision and Tool Call."""

from typing import Any, Literal
from pydantic import BaseModel


class ToolCall(BaseModel):
    """A single tool call within a Reasoner Decision."""

    tool: str
    arguments: dict[str, Any]
    policy_basis: list[str]


class ReasonerDecision(BaseModel):
    """Structured output produced by the Reasoner; expresses intent only."""

    action: Literal["allow", "deny", "escalate", "clarify"]
    tool_calls: list[ToolCall]
    reasoning: str
    cited_sections: list[str]
    user_message_draft: str
