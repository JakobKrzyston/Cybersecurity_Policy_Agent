"""Mock tool: reset_password."""


def reset_password(account_id: str) -> dict:
    """Reset the password for the given account.

    Args:
        account_id: The account whose password to reset.

    Returns:
        Dict with 'status' and 'account_id'.
    """
    return {"status": "reset", "account_id": account_id}
