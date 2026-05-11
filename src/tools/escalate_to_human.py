"""Mock tool: escalate_to_human."""


def escalate_to_human(reason: str, session_id: str) -> dict:
    """Escalate the current request to a human agent.

    Args:
        reason: Why the request is being escalated.
        session_id: The session identifier for the ticket.

    Returns:
        Dict with 'status', 'ticket_id', and 'reason'.
    """
    return {"status": "escalated", "ticket_id": "TICKET-001", "reason": reason}
