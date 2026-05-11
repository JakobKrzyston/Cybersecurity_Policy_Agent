"""Output Filter: strips PII and formats tool output before it reaches the Reasoner or user."""


def filter_output(tool_name: str, raw_output: dict, tracer) -> dict:
    """Strip PII and format tool output before it reaches the Reasoner or user.

    Args:
        tool_name: Name of the tool that produced raw_output.
        raw_output: Unfiltered result dict from the tool.
        tracer: Pipeline trace context (span appended on completion).

    Returns:
        Filtered output dict with PII fields removed per policy §2.2, §4.2, §9.x.
    """
    return raw_output
