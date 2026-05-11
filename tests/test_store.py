"""PersistentStore tests: SQLite rate-limit tracking behaviors."""

import time

import pytest

from src.infra.store import InMemoryRateLimitStore, RateLimitStore, SQLiteRateLimitStore


def test_sqlite_store_records_and_counts(tmp_path):
    store = SQLiteRateLimitStore(str(tmp_path / "rate.db"))
    store.record_action("alice", "reset_password")
    assert store.count_recent("alice", "reset_password", window_days=30) == 1


def test_sqlite_store_survives_restart(tmp_path):
    db_path = str(tmp_path / "rate.db")
    store1 = SQLiteRateLimitStore(db_path)
    store1.record_action("alice", "reset_password")

    store2 = SQLiteRateLimitStore(db_path)
    assert store2.count_recent("alice", "reset_password", window_days=30) == 1


def test_count_recent_excludes_actions_older_than_window(tmp_path, monkeypatch):
    db_path = str(tmp_path / "rate.db")
    store = SQLiteRateLimitStore(db_path)

    # Record an action 31 days in the past
    old_ts = time.time() - (31 * 24 * 3600)
    monkeypatch.setattr("src.infra.store.time", type("T", (), {"time": staticmethod(lambda: old_ts)})())
    store.record_action("alice", "reset_password")
    monkeypatch.undo()

    assert store.count_recent("alice", "reset_password", window_days=30) == 0


def test_inmemory_store_satisfies_protocol():
    store = InMemoryRateLimitStore()
    assert isinstance(store, RateLimitStore)
