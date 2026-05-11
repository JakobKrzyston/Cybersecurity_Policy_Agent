"""Instrumented LLM wrapper: captures token counts, cost, and retries per ADR-0002."""


def instrumented_llm_call(model_id: str, messages: list, tracer) -> dict:
    raise NotImplementedError
