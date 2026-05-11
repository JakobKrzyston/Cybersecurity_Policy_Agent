"""Persistent Store: SQLite-backed cross-session rate-limit tracking.

Exports: RateLimitStore, InMemoryRateLimitStore, SQLiteRateLimitStore.
"""

import sqlite3
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimitStore(Protocol):
    """Interface for rate-limit tracking; injectable for testing."""

    def count_recent(self, identity: str, tool_name: str, window_days: int) -> int:
        """Return the number of tool_name actions for identity within the rolling window."""
        ...

    def record_action(self, identity: str, tool_name: str) -> None:
        """Record that identity performed tool_name at the current time."""
        ...


class InMemoryRateLimitStore:
    """In-memory rate-limit store for testing and golden-test injection.

    Args:
        None
    """

    def __init__(self) -> None:
        self._records: list[tuple[str, str, float]] = []

    def count_recent(self, identity: str, tool_name: str, window_days: int) -> int:
        """Count actions for identity/tool_name within the rolling window."""
        cutoff = time.time() - window_days * 24 * 3600
        return sum(
            1 for id_, tool, ts in self._records
            if id_ == identity and tool == tool_name and ts >= cutoff
        )

    def record_action(self, identity: str, tool_name: str) -> None:
        """Record that identity performed tool_name now."""
        self._records.append((identity, tool_name, time.time()))


class SQLiteRateLimitStore:
    """SQLite-backed rate-limit store; persists cross-session and survives restart.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rate_limits "
                "(identity TEXT NOT NULL, tool_name TEXT NOT NULL, timestamp REAL NOT NULL)"
            )

    def count_recent(self, identity: str, tool_name: str, window_days: int) -> int:
        """Return the number of tool_name actions for identity within the rolling window."""
        cutoff = time.time() - window_days * 24 * 3600
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM rate_limits "
                "WHERE identity = ? AND tool_name = ? AND timestamp >= ?",
                (identity, tool_name, cutoff),
            ).fetchone()
        return row[0]

    def record_action(self, identity: str, tool_name: str) -> None:
        """Record that identity performed tool_name at the current time."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO rate_limits (identity, tool_name, timestamp) VALUES (?, ?, ?)",
                (identity, tool_name, time.time()),
            )
