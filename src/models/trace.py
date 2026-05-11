"""Pipeline trace models: PipelineSpan and Tracer (support bundle building block)."""

from typing import Any
from pydantic import BaseModel, Field


class PipelineSpan(BaseModel):
    """One component's contribution to the pipeline trace."""

    name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    latency_ms: float


class Tracer(BaseModel):
    """Accumulates pipeline spans across all components for a single request."""

    spans: list[PipelineSpan] = Field(default_factory=list)

    def append_span(self, span: PipelineSpan) -> None:
        """Append a component span to the running trace."""
        self.spans.append(span)
