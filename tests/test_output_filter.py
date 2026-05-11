"""Output Filter tests: PII stripping and trace sanitization per §2.2, §4.2, §1.3.a."""

from src.models.trace import Tracer
from src.pipeline.output_filter import filter_output


def test_lookup_employee_strips_personal_email():
    raw = {
        "employee_id": "alice",
        "name": "Alice Smith",
        "work_email": "alice@gaggia.com",
        "personal_email": "alice@gmail.com",
    }
    result = filter_output("lookup_employee", raw, tracer=None)
    assert "personal_email" not in result


def test_lookup_employee_strips_personal_phone():
    raw = {
        "employee_id": "alice",
        "name": "Alice Smith",
        "work_phone": "555-0100",
        "personal_phone": "555-9999",
    }
    result = filter_output("lookup_employee", raw, tracer=None)
    assert "personal_phone" not in result


def test_lookup_employee_strips_home_address():
    raw = {
        "employee_id": "alice",
        "name": "Alice Smith",
        "office_location": "London",
        "home_address": "123 Main St, London",
    }
    result = filter_output("lookup_employee", raw, tracer=None)
    assert "home_address" not in result


def test_lookup_employee_keeps_safe_fields():
    raw = {
        "employee_id": "alice",
        "name": "Alice Smith",
        "work_email": "alice@gaggia.com",
        "work_phone": "555-0100",
        "office_location": "London",
        "personal_email": "alice@gmail.com",
        "personal_phone": "555-9999",
        "home_address": "123 Main St",
    }
    result = filter_output("lookup_employee", raw, tracer=None)
    assert result["employee_id"] == "alice"
    assert result["name"] == "Alice Smith"
    assert result["work_email"] == "alice@gaggia.com"
    assert result["work_phone"] == "555-0100"
    assert result["office_location"] == "London"


def test_reset_password_strips_temporary_password():
    raw = {"status": "reset", "account_id": "alice", "temporary_password": "Tmp$ecret1"}
    result = filter_output("reset_password", raw, tracer=None)
    assert "temporary_password" not in result
    assert result["status"] == "reset"
    assert result["account_id"] == "alice"


def test_query_hr_database_strips_compensation_from_results():
    raw = {
        "query": "SELECT * FROM employees WHERE id='alice'",
        "results": [
            {"employee_id": "alice", "name": "Alice Smith", "compensation": 120000},
        ],
    }
    result = filter_output("query_hr_database", raw, tracer=None)
    assert "compensation" not in result["results"][0]
    assert result["results"][0]["employee_id"] == "alice"


def test_query_hr_database_strips_hr_sensitive_fields():
    raw = {
        "query": "SELECT * FROM employees WHERE id='alice'",
        "results": [
            {
                "employee_id": "alice",
                "name": "Alice Smith",
                "performance_rating": "exceeds",
                "disciplinary_notes": "written warning 2024-01",
            },
        ],
    }
    result = filter_output("query_hr_database", raw, tracer=None)
    record = result["results"][0]
    assert "performance_rating" not in record
    assert "disciplinary_notes" not in record
    assert record["employee_id"] == "alice"


def test_unknown_tool_passes_through_unchanged():
    raw = {"status": "ok", "some_field": "value"}
    result = filter_output("some_future_tool", raw, tracer=None)
    assert result == {"status": "ok", "some_field": "value"}


def test_tracer_span_is_appended():
    tracer = Tracer()
    raw = {"employee_id": "alice", "name": "Alice Smith"}
    filter_output("lookup_employee", raw, tracer=tracer)
    assert len(tracer.spans) == 1
    assert tracer.spans[0].name == "output_filter"


def test_tracer_span_does_not_contain_raw_pii():
    tracer = Tracer()
    raw = {
        "employee_id": "alice",
        "name": "Alice Smith",
        "personal_email": "alice@gmail.com",
        "home_address": "123 Main St",
    }
    filter_output("lookup_employee", raw, tracer=tracer)
    span = tracer.spans[0]
    # inputs must not carry the raw PII fields
    assert "personal_email" not in span.inputs
    assert "home_address" not in span.inputs
    # outputs carry only the filtered result — PII fields absent
    filtered = span.outputs["filtered_output"]
    assert "personal_email" not in filtered
    assert "home_address" not in filtered
