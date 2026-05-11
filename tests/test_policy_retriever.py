"""Policy Retriever tests: chunking, ChromaDB retrieval, cross-reference expansion."""

from __future__ import annotations

import pytest
from src.pipeline.chunker import chunk_policy, PolicyChunk
from src.pipeline.policy_retriever import ChromaDBRetriever, PolicyRetrieverBase


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------

POLICY_SNIPPET = """\
### 1 Account Management
**Tags:** authentication, password_reset
**Applies to:** all users
**Related sections:** 5.1, 6.1

The agent administers credential lifecycle.

1.1. The agent may reset passwords for standard employee accounts.
  1.1.a. Before performing the reset, the agent must verify identity.
  1.1.b. At most three resets per account per rolling 30-day window.
"""


def test_chunk_policy_produces_clause_level_chunk_with_correct_id():
    chunks = chunk_policy(POLICY_SNIPPET)
    ids = [c.id for c in chunks]
    assert "1.1.b" in ids


def test_chunk_text_is_prefixed_with_section_header_tags_and_related():
    chunks = chunk_policy(POLICY_SNIPPET)
    chunk = next(c for c in chunks if c.id == "1.1.b")
    assert "### 1 Account Management" in chunk.text
    assert "Tags:" in chunk.text
    assert "Related sections:" in chunk.text


def test_chunk_carries_tags_from_parent_section():
    chunks = chunk_policy(POLICY_SNIPPET)
    chunk = next(c for c in chunks if c.id == "1.1.a")
    assert "authentication" in chunk.tags
    assert "password_reset" in chunk.tags


# ---------------------------------------------------------------------------
# Retriever tests (uses real ChromaDB + sentence-transformers in-process)
# ---------------------------------------------------------------------------

POLICY_PATH = "gaggia_helpdesk_policy.md"


@pytest.fixture(scope="module")
def retriever():
    with open(POLICY_PATH) as f:
        policy_text = f.read()
    return ChromaDBRetriever.from_policy_text(policy_text)


def test_retriever_is_policy_retriever_base(retriever):
    assert isinstance(retriever, PolicyRetrieverBase)


def test_retriever_returns_policy_chunks_with_id_and_text(retriever):
    results = retriever.retrieve("password reset", top_k=3)
    assert len(results) > 0
    for chunk in results:
        assert isinstance(chunk, PolicyChunk)
        assert chunk.id
        assert chunk.text


def test_querying_password_reset_returns_section_1_chunks(retriever):
    results = retriever.retrieve("reset my password", top_k=5)
    section_ids = [c.id for c in results]
    # At least one result should be from section 1 (account management / password reset)
    assert any(chunk_id.startswith("1.") for chunk_id in section_ids)


def test_tag_filter_restricts_initial_retrieval_to_matching_tag(retriever):
    # "byod" only appears in sections 8 and 10.
    # Section 1 (password_reset) has no byod tag and is not reachable via cross-reference
    # expansion from byod chunks, so it must not appear in results.
    results = retriever.retrieve("reset my password", tags=["byod"], top_k=5)
    result_ids = [c.id for c in results]
    assert all(not cid.startswith("1.") for cid in result_ids), (
        f"Section 1 chunks should not appear when filtering by 'byod': {result_ids}"
    )


# ---------------------------------------------------------------------------
# Cross-reference expansion tests (pure logic via minimal in-memory fixture)
# ---------------------------------------------------------------------------

from src.pipeline.policy_retriever import _expand_cross_references


def _make_chunk(chunk_id: str, tags: list[str], related: list[str] | None = None) -> PolicyChunk:
    related_str = ", ".join(related) if related else ""
    text = f"### {chunk_id.split('.')[0]} Section\n**Tags:** {', '.join(tags)}\n"
    if related_str:
        text += f"**Related sections:** {related_str}\n"
    text += "\nClause text."
    return PolicyChunk(id=chunk_id, text=text, tags=tags)


def test_cross_reference_expansion_adds_related_chunk_when_tags_intersect():
    # 1.1 references 2.1; both share tag "auth" → 2.1 should be added
    chunk_1_1 = _make_chunk("1.1", ["auth", "password_reset"], related=["2.1"])
    chunk_2_1 = _make_chunk("2.1", ["auth", "directory"], related=None)
    index = {"1.1": chunk_1_1, "2.1": chunk_2_1}

    result = _expand_cross_references([chunk_1_1], index)
    result_ids = [c.id for c in result]

    assert "2.1" in result_ids


def test_cross_reference_expansion_excludes_related_chunk_with_no_tag_overlap():
    # 1.1 references 5.1; they share NO tags → 5.1 should NOT be added
    chunk_1_1 = _make_chunk("1.1", ["password_reset", "account_types"], related=["5.1"])
    chunk_5_1 = _make_chunk("5.1", ["escalation", "incident_reporting"], related=None)
    index = {"1.1": chunk_1_1, "5.1": chunk_5_1}

    result = _expand_cross_references([chunk_1_1], index)
    result_ids = [c.id for c in result]

    assert "5.1" not in result_ids
