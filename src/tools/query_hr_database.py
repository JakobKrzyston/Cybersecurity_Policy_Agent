"""Mock tool: query_hr_database."""


def query_hr_database(query: str) -> dict:
    """Run a mock HR database query.

    Args:
        query: The query string to execute.

    Returns:
        Dict with 'query' and 'results' (empty list in mock).
    """
    return {"query": query, "results": []}
