# Cybersecurity_Policy_Agent

## Problem Description

AI agents that take actions on behalf of users need to operate within policy constraints. In practice, policy documents are written in natural language, contain ambiguity, and don't cover every edge case. When an agent misinterprets a policy either by doing something it shouldn't or refusing something it should the consequences range from annoying to dangerous.

*Build an agent that can answer questions and take actions on behalf of employees at a fictional company, **operating strictly within a written policy***, while handling the ambiguity and adversarial inputs that come with real-world use.

## Notable design considerations
### Agent Topology
This framework is designed to:
- Have deterministic systems in place for mission-critical points
- Independent restriction enforcement on the reasoning at the beginning of the pipeline and when calling tools
- A bug when filtering of outputs does not effect the reasoning
- Isolate LLM development/testing by use case
- Isolate tool development/testing

1. Trust Gate (deterministic code)
First thing every request hits. Takes (request, trust_tier) and applies hard rules:
- Team Red → only escalate_to_human is reachable, full stop
- Team Grey → flag the request for elevated caution, pass through
- Team Blue → pass through

2. Policy Retriever (LLM API call + vector store)
- Takes the request, returns the top-k relevant policy sections with their cross-references
- This is its own component because (a) we want to inspect what got retrieved when debugging, and (b) it should be swappable
- Hybrid retrieval --> semantic + tag filter + cross-reference expansion

3. Reasoner Agent (LLM)
- The main agent
- Receives: request, trust tier, retrieved policy sections
- Outputs a structured decision: {action: allow|deny|escalate|clarify, tool_calls: [...], reasoning: "...", cited_sections: [...], user_message_draft: "..."}
- Critical: it outputs intent, not execution. It says "I want to call lookup_employee('Sarah Chen')" but doesn't actually call it. This separation allows for cleaner tool calls and traceability/auditability

4. Tool Executor (deterministic + LLM-assisted filtering)
Receives the reasoner's intended tool calls. For each one:
- Re-checks the trust gate (redundancy on purpose)
- Executes the mock tool
- Passes the raw output through the Output Filter (next agent) before anything else sees it

5. Output Filter (rule-based)
- Takes raw tool output + policy context, returns sanitized output
- For lookup_employee this means stripping personal_email, personal_phone, home_address, salary, performance_rating, employment_status.

### Cost & Latency Awareness
This is not only important for monitoring spend, evaluating performance, etc. but is crucial when right-sizing model selection per task
For every API call there should be a structured log including:
- Latency = end_time - start_time
- Input, output, cached tokens
- Tokens costs (input/output/cached, NOT including tools)
- Retries (Not including tool retries)
- Total number of tools called
- Total cost of tools called
- Tools called (list)
- Cost of tools called (list)
- Latency of tool calls (list)
- Input/Output/Cached tokens per tool call
- Cost of tokens per tool call
- Retries per tool call
Note: The cost should be calculated based on the number of tokens and reference the prices which can be stored in a file
