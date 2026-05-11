# ADR-0002: Every request produces a full pipeline trace (support bundle)

## Status
Accepted

## Context
The pipeline has five components (Trust Gate, Policy Retriever, Reasoner, Tool Executor, Output Filter). Each component makes decisions that affect the final outcome. Debugging failures, auditing policy compliance (section 14), and evaluating correctness all require visibility into every component's inputs, outputs, and timing — not just the final response.

## Decision
Every request produces a single structured trace object that spans the entire pipeline. Each component appends its own span to the trace:
- **Component name**
- **Inputs** (sanitized — no raw credentials)
- **Outputs**
- **Latency** (end_time - start_time)
- For LLM components additionally: input/output/cached tokens, cost (from `model_prices.json`), retries
- For tool calls additionally: tool name, arguments, raw result, filtered result, latency, token cost

The trace is written as a single JSON object to a structured log at request completion. This log is the "support bundle" — the authoritative artifact for monitoring, evaluation, debugging, and audit.

LLM calls go through a shared `instrumented_llm_call()` wrapper that captures token and cost data automatically. Non-LLM components self-report their span via a shared `Tracer` context object passed through the pipeline.

## Consequences
- Full end-to-end visibility per request with a single artifact
- Audit log per policy section 14 is a derived view of the trace, not a separate system
- Golden test evaluation can assert against trace fields (cited_sections, action, tool outputs) not just the final user message
- Every component must accept and return the Tracer object — mild coupling, but intentional
- Sensitive fields (passwords, PII in tool results) must be explicitly excluded from trace inputs/outputs at the Output Filter boundary
