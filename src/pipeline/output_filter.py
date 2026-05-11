"""Output Filter: strips PII and formats tool output before it reaches the Reasoner or user."""

import time

from src.models.trace import PipelineSpan

# Fields stripped per §2.2 (personal contact info).
_LOOKUP_EMPLOYEE_STRIP = {"personal_email", "personal_phone", "home_address"}
# Fields stripped per §4.2 (compensation, performance, disciplinary records).
_HR_SENSITIVE_STRIP = {"compensation", "performance_rating", "disciplinary_notes"}


def filter_output(tool_name: str, raw_output: dict, tracer) -> dict:
    """Strip PII and format tool output before it reaches the Reasoner or user.

    Args:
        tool_name: Name of the tool that produced raw_output.
        raw_output: Unfiltered result dict from the tool.
        tracer: Pipeline trace context (span appended on completion).

    Returns:
        Filtered output dict with PII fields removed per policy §2.2, §4.2, §9.x.
    """
    start = time.monotonic()

    if tool_name == "lookup_employee":
        for field in _LOOKUP_EMPLOYEE_STRIP:
            raw_output.pop(field, None)
    elif tool_name == "reset_password":
        raw_output.pop("temporary_password", None)
    elif tool_name == "query_hr_database":
        for record in raw_output.get("results", []):
            for field in _HR_SENSITIVE_STRIP:
                record.pop(field, None)

    if tracer is not None:
        tracer.append_span(PipelineSpan(
            name="output_filter",
            inputs={"tool_name": tool_name},
            outputs={"filtered_output": raw_output},
            latency_ms=(time.monotonic() - start) * 1000,
        ))

    return raw_output
