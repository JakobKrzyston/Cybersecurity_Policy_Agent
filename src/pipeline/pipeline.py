"""Pipeline: wires all five components and writes a trace log entry per request."""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.infra.store import RateLimitStore
from src.models.decision import ReasonerDecision
from src.models.session import Session, SessionContext
from src.models.trace import PipelineSpan, Tracer
from src.pipeline import citation_grounding, reasoner, tool_executor, trust_gate
from src.pipeline.policy_retriever import PolicyRetrieverBase


@dataclass
class PipelineResult:
    """Structured output of a single pipeline run."""

    decision: ReasonerDecision
    tool_results: list[dict] = field(default_factory=list)
    trust_tier: str = ""
    risk: str = ""


class Pipeline:
    """Wires Trust Gate → Policy Retriever → Reasoner → Citation Grounding → Tool Executor.

    Args:
        blocklist: Blocklist implementation for the Trust Gate.
        retriever: Policy retriever implementation.
        registry: Mapping of tool name to callable for the Tool Executor.
        llm_call_fn: Optional LLM call override; defaults to instrumented_llm_call.
    """

    def __init__(
        self,
        *,
        blocklist,
        retriever: PolicyRetrieverBase,
        registry: dict,
        store: Optional[RateLimitStore] = None,
        llm_call_fn: Optional[Callable] = None,
    ) -> None:
        self._blocklist = blocklist
        self._retriever = retriever
        self._registry = registry
        self._store = store
        self._llm_call_fn = llm_call_fn

    def run(
        self,
        request: str,
        session: Session,
        context: SessionContext,
        tracer: Tracer,
    ) -> PipelineResult:
        """Execute the full pipeline for one request.

        Args:
            request: Raw user request string.
            session: In-memory session accumulating request history.
            context: Live session signals for Trust Gate classification.
            tracer: Shared trace context; each component appends its span.

        Returns:
            PipelineResult containing the decision, tool results, trust tier, and risk.
        """
        # Trust Gate
        t0 = time.monotonic()
        tier, risk = trust_gate.run(session, context, self._blocklist, tracer=None)
        tracer.append_span(PipelineSpan(
            name="trust_gate",
            inputs={"identity": context.identity, "device_type": context.device_type},
            outputs={"trust_tier": tier, "risk": risk},
            latency_ms=(time.monotonic() - t0) * 1000,
        ))

        # Policy Retriever
        t1 = time.monotonic()
        chunks = self._retriever.retrieve(request)
        retrieved_ids = {c.id for c in chunks}
        tracer.append_span(PipelineSpan(
            name="policy_retriever",
            inputs={"query": request},
            outputs={"chunk_ids": list(retrieved_ids), "chunk_count": len(chunks)},
            latency_ms=(time.monotonic() - t1) * 1000,
        ))

        # Reasoner
        decision = reasoner.reason(
            session=session,
            policy_chunks=chunks,
            tracer=tracer,
            user_request=request,
            trust_tier=tier,
            risk=risk,
            llm_call_fn=self._llm_call_fn,
        )

        # Citation Grounding
        decision = citation_grounding.check_citation_grounding(decision, retrieved_ids)

        # Tool Executor
        tool_results: list[dict] = []
        if decision.action == "allow" and decision.tool_calls:
            try:
                tool_results = tool_executor.execute(
                    decision=decision,
                    trust_tier=tier,
                    risk=risk,
                    registry=self._registry,
                    tracer=tracer,
                    store=self._store,
                    identity=context.identity,
                )
            except PermissionError as exc:
                # Executor independently enforces rate limits and red-risk constraints.
                # If it rejects after the Reasoner said allow, escalate rather than crash.
                decision = ReasonerDecision(
                    action="escalate",
                    tool_calls=[],
                    reasoning=str(exc),
                    cited_sections=decision.cited_sections,
                    user_message_draft=f"Request escalated: {exc}",
                )

        _write_trace(tracer)
        return PipelineResult(decision=decision, tool_results=tool_results, trust_tier=tier, risk=risk)


def _write_trace(tracer: Tracer) -> None:
    log_path = os.environ.get("PIPELINE_LOG", "pipeline.log")
    total_latency_ms = sum(s.latency_ms for s in tracer.spans)
    total_cost = sum(s.outputs.get("cost", 0.0) for s in tracer.spans)
    entry = json.dumps({
        "total_latency_ms": total_latency_ms,
        "total_cost": f"{total_cost:.6f}",
        "spans": [s.model_dump() for s in tracer.spans],
    })
    with open(log_path, "a") as f:
        f.write(entry + "\n")
