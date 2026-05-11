# ADR-0001: Reasoner outputs custom JSON, not native tool_use

## Status
Accepted

## Context
The Reasoner agent needs to express *intent* (what tools to call, what decision was reached) without executing those actions itself. The Anthropic API provides a native `tool_use` mechanism that already separates intent from execution. However, it is provider-specific.

## Decision
The Reasoner outputs a custom JSON blob with this shape:
```json
{
  "action": "allow|deny|escalate|clarify",
  "tool_calls": [...],
  "reasoning": "...",
  "cited_sections": [...],
  "user_message_draft": "..."
}
```
The Tool Executor parses this blob and re-validates before executing any tool call. No native tool_use API is used.

## Consequences
- **Provider-agnostic**: the Reasoner can be swapped to any model that produces structured JSON output (OpenAI, Gemini, local models, etc.)
- **Schema enforcement is our responsibility**: we must validate the JSON ourselves; we don't get the API's built-in argument validation for free
- **Traceability**: the full structured decision is logged at the Reasoner boundary, making auditing straightforward per policy section 14
- **Cost**: reimplements what the Anthropic tool_use mechanism provides natively
