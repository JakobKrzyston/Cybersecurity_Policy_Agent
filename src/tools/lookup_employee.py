"""Mock tool: lookup_employee."""


def lookup_employee(employee_id: str) -> dict:
    """Return mock employee record for the given ID.

    Args:
        employee_id: The employee identifier to look up.

    Returns:
        Dict with 'employee_id', 'name', and 'email'.
    """
    return {"employee_id": employee_id, "name": "Mock Employee", "email": f"{employee_id}@example.com"}
