"""Mock tool: grant_file_access."""


def grant_file_access(employee_id: str, resource: str) -> dict:
    """Grant the given employee access to the specified resource.

    Args:
        employee_id: The employee to grant access.
        resource: The resource path or identifier to grant access to.

    Returns:
        Dict with 'status', 'employee_id', and 'resource'.
    """
    return {"status": "granted", "employee_id": employee_id, "resource": resource}
