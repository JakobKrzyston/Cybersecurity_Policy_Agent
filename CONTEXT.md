# Context

Domain language for the Gaggia Helpdesk Policy Agent.

## Glossary

### Reasoner Decision
The structured JSON output the Reasoner produces. Shape: `{action, tool_calls, reasoning, cited_sections, user_message_draft}`. Expresses *intent* only — the Tool Executor re-validates and executes. Never uses native API tool_use (see ADR-0001).

### Tool Executor
Deterministic component. Receives the Reasoner Decision, re-runs the Trust Gate check on each intended tool call, then executes the mock tool. No LLM involved. Passes raw output to the Output Filter before anything else sees it.

### Citation Grounding
A deterministic validation step run after the Reasoner produces its Decision and before the Tool Executor acts on it. Checks that every section ID in `cited_sections` and every `policy_basis` entry appears in the set of chunk IDs returned by the Policy Retriever for this request. Citations not present in retrieved chunks are flagged as potential hallucinations — the request is escalated rather than executed. Adds a layer of hallucination resistance that scales as the policy grows. Implemented as a Pydantic validator or a standalone validation function in the pipeline, not an LLM call.

### Reasoner System Prompt
Built per-request from: (1) agent role/persona, (2) retrieved policy chunks formatted with explicit section IDs, (3) session trust tier and risk classification, (4) tool registry description. User message carries only the request. Designed so the Reasoner cites section IDs it can see in its context, enabling Citation Grounding to catch any hallucinated citations.

### Tool Call (Reasoner Decision field)
Each entry in `tool_calls` within a Reasoner Decision. Schema:
```json
{ "tool": "<tool_name>", "arguments": { ... }, "policy_basis": ["<section>", ...] }
```
`policy_basis` declares which policy sections authorize the tool call. The Tool Executor uses it as a secondary citation check; the LLM-as-judge uses it to evaluate whether the Reasoner cited correctly. Enforced by Pydantic.

### Project Structure
```
src/
  pipeline/   trust_gate, policy_retriever, reasoner, tool_executor, output_filter
  tools/      one file per mock tool (reset_password, lookup_employee, grant_file_access, query_hr_database, escalate_to_human)
  models/     decision.py (Pydantic schemas), session.py, trace.py
  infra/      llm.py (instrumented wrapper), store.py (SQLite), embeddings.py (ChromaDB)
  config/     model_prices.json
  evaluation/ golden_cases/, judge.py, runner.py
tests/        test_trust_gate.py, test_output_filter.py, test_golden.py
```

### Model Configuration
Models are configurable at runtime, not hardcoded. Two distinct roles: Reasoner (capable model for policy reasoning and structured JSON output) and LLM-as-judge (different model to avoid self-grading bias in evaluation). Model IDs and prices sourced from `model_prices.json`. Supports provider-agnosticism per ADR-0001.

### Pipeline Trace (Support Bundle)
A single structured JSON object produced per request, spanning all five pipeline components. Each component appends a span with: name, inputs, outputs, latency. LLM spans additionally include token counts, cost, and retries. Tool call spans additionally include tool name, arguments, raw result, filtered result. Written to a structured log at request completion. Serves as the authoritative artifact for monitoring, evaluation, debugging, and policy-section-14 audit. Sensitive fields are excluded at the Output Filter boundary. See ADR-0002.

### Tracer
A context object passed through the pipeline that each component uses to append its span to the Pipeline Trace. Shared infrastructure — every component accepts and returns it.

### Session
An in-memory object accumulating request history for the duration of a conversation. Enables enforcement of intra-session policy rules (5.3.c cumulative ambiguity, 7.3 pattern detection). Passed into the Trust Gate and Reasoner on each request. Distinct from the persistent store.

### Persistent Store
A lightweight SQLite database tracking cross-session state required by rate-limit rules (e.g., 1.1.b: max 3 password resets per account per rolling 30-day window). Not used for conversation history — only for facts that must survive across sessions.

### Runtime Stack
Python. Key libraries: `anthropic` (LLM API), `chromadb` (vector store), `pydantic` (Reasoner Decision schema validation), `pytest` (golden test set). Reasoner Decision JSON is validated by Pydantic before the Tool Executor touches it.

### Evaluation Strategy
Two-track: (1) Golden test set — hand-crafted scenarios with expected `action`, `cited_sections`, and `user_message_draft`; runs in CI as a regression suite. (2) LLM-as-judge — a separate evaluation model scores Reasoner Decisions against policy for edge cases not covered by the golden set. Golden set catches regressions; LLM-as-judge explores coverage.

### Policy Retriever
The second pipeline component. Performs hybrid retrieval: semantic search via ChromaDB (local, in-process) + tag filter + one-hop cross-reference expansion (see Cross-Reference Expansion). Returns top-k policy chunks with their identifiers to the Reasoner. Designed to be swappable — accessed through an abstraction layer, not called directly.

### Cross-Reference Expansion
One-hop expansion of retrieved policy chunks, gated by tag intersection. After semantic retrieval returns top-k chunks, each chunk's "Related sections" are added only if the referenced section shares at least one tag with the originating chunk. Prevents context explosion from section 5 (escalation), which is cross-referenced by nearly every action clause.

### Policy Chunk
The unit of retrieval. Each numbered clause (e.g., 1.1.b) stored as its own chunk, prefixed with its parent section header (tags, applies-to, related sections). Chunk identifiers map directly to policy section numbers (e.g., "1.1.b") so the Reasoner can cite them per policy 6.1. See: Policy Retriever, Cross-Reference Expansion.

### Mock Tool Registry
The fixed set of tools the Reasoner may reference and the Tool Executor may execute. Initial scope: `reset_password`, `lookup_employee`, `grant_file_access`, `query_hr_database`, `escalate_to_human`. All other policy-implied operations are out of scope for initial implementation.

### Output Filter
Rule-based component. Strips PII and formats tool output before it reaches the Reasoner or the user. Operates as a fixed map of `tool_name → fields_to_strip/transform`. No LLM involved. Covers explicit prohibitions from policy section 2.2, 4.2, 9.x.

### Risk Classification
A behavioral/intent label assigned to a session, orthogonal to trust tier. Values: `red` (treat as adversarial — only `escalate_to_human` reachable), `grey` (elevated caution, pass through with flags), `blue` (no elevated risk signal). A fully-authenticated verified manager can be classified `red` if IT Security has flagged them or if the session shows social engineering signals. Determined by the Trust Gate.

**Avoid:** "team color" as a standalone term — always pair with "risk classification" to avoid confusion with authentication level.

**Current scope:** Risk classification sourced from an external IT Security blocklist/watchlist register only. In-session behavioral heuristics are out of scope for initial implementation. Must have tests covering: identity on blocklist → `red` routing, identity not on blocklist → `blue` default, blocklist lookup failure → fail-safe behavior (TBD).

### Trust Gate
The first component every request passes through. Responsible for both *determining* and *enforcing* the session's trust tier. Reads raw session signals (SSO assertion, MFA recency, device compliance, directory state) and classifies the session before any LLM reasoning occurs. Deterministic code — no LLM involved.

### Trust Tier
A classification of a session derived by the Trust Gate from live signals. Defined by policy section 15. Values: `anonymous`, `verified_employee`, `verified_manager`, `managed_device`, `delegated`. Governs which actions the agent may perform for the duration of that request. Re-evaluated per-request, not per-session.
