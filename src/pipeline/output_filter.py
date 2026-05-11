"""Output Filter: strips PII and formats tool output before it reaches the Reasoner or user."""


def filter_output(tool_name: str, raw_output: dict, tracer) -> dict:
    raise NotImplementedError
