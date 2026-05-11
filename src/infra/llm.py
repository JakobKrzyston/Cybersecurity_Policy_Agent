"""Instrumented LLM wrapper: captures token counts, cost, and retries per ADR-0002."""

import time
from typing import Any, Optional

import anthropic

from src.config.config import load_model_prices
from src.models.trace import PipelineSpan, Tracer


def instrumented_llm_call(
    model_id: str,
    messages: list,
    tracer: Tracer,
    client: Any = None,
    system: Optional[str] = None,
) -> dict[str, Any]:
    """Wrap an Anthropic API call, capturing metrics and appending an LLM span to the tracer.

    Args:
        model_id: Anthropic model identifier for the call.
        messages: Message list in Anthropic messages API format (user/assistant turns only).
        tracer: Pipeline trace context; an LLM span is appended on completion.
        client: Anthropic client instance; defaults to anthropic.Anthropic().
        system: Optional system prompt string; sent with ephemeral cache_control if provided.

    Returns:
        Dict with keys: content, input_tokens, output_tokens, cached_tokens, cost, retries, model_id.
    """
    if client is None:
        client = anthropic.Anthropic()

    prices = load_model_prices()
    model_prices = prices.get(model_id, {"input_price_per_token": 0.0, "output_price_per_token": 0.0})

    kwargs: dict[str, Any] = {"model": model_id, "max_tokens": 1024, "messages": messages}
    if system is not None:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    start = time.monotonic()
    retries = 0
    response = client.messages.create(**kwargs)
    latency_ms = (time.monotonic() - start) * 1000

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cached_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cost = (
        input_tokens * model_prices["input_price_per_token"]
        + output_tokens * model_prices["output_price_per_token"]
    )
    content = response.content[0].text

    span = PipelineSpan(
        name="llm",
        inputs={"model_id": model_id, "message_count": len(messages)},
        outputs={
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cost": cost,
            "retries": retries,
        },
        latency_ms=latency_ms,
    )
    if tracer is not None:
        tracer.append_span(span)

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cost": cost,
        "retries": retries,
        "model_id": model_id,
    }
