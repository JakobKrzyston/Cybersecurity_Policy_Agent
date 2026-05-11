"""Policy Retriever: hybrid semantic + tag retrieval of policy chunks from ChromaDB."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

import chromadb
from chromadb.utils import embedding_functions

from src.pipeline.chunker import PolicyChunk, chunk_policy

_RELATED_RE = re.compile(r"\*\*Related sections:\*\*\s*(.+)")


class PolicyRetrieverBase(ABC):
    """Abstraction layer — no pipeline component outside this module imports ChromaDB."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[PolicyChunk]:
        """Return top-k policy chunks relevant to query, optionally filtered by tags.

        Args:
            query: Natural language request to match against policy.
            tags: If provided, restrict results to chunks sharing at least one tag.
            top_k: Maximum number of chunks to return before expansion.

        Returns:
            List of PolicyChunk objects ordered by relevance.
        """


class ChromaDBRetriever(PolicyRetrieverBase):
    """In-process ChromaDB-backed retriever using sentence-transformers embeddings."""

    def __init__(self, collection: chromadb.Collection, chunks_by_id: dict[str, PolicyChunk]) -> None:
        self._collection = collection
        self._chunks_by_id = chunks_by_id

    @classmethod
    def from_policy_text(cls, policy_text: str) -> "ChromaDBRetriever":
        """Build a retriever from raw policy markdown.

        Args:
            policy_text: Full content of the policy document.

        Returns:
            Populated ChromaDBRetriever ready to query.
        """
        chunks = chunk_policy(policy_text)
        chunks_by_id = {c.id: c for c in chunks}

        client = chromadb.EphemeralClient()
        ef = embedding_functions.DefaultEmbeddingFunction()
        collection = client.get_or_create_collection(
            name="policy",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

        collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{"tags": ",".join(c.tags)} for c in chunks],
        )

        return cls(collection, chunks_by_id)

    def retrieve(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[PolicyChunk]:
        """Return top-k chunks by cosine similarity, optionally filtered by tag.

        Args:
            query: Natural language request to match against policy.
            tags: If provided, restrict results to chunks sharing at least one tag.
            top_k: Maximum number of chunks to return before cross-reference expansion.

        Returns:
            List of PolicyChunk objects, deduplicated, ordered by relevance.
        """
        # Fetch more than top_k when tag filtering so we can trim after Python-side filtering
        fetch_n = min(self._collection.count(), top_k * 4 if tags else top_k)
        results = self._collection.query(query_texts=[query], n_results=fetch_n)

        ids = results["ids"][0]
        retrieved = [self._chunks_by_id[cid] for cid in ids if cid in self._chunks_by_id]

        if tags:
            tag_set = set(tags)
            retrieved = [c for c in retrieved if tag_set & set(c.tags)]
            retrieved = retrieved[:top_k]

        return _expand_cross_references(retrieved, self._chunks_by_id)


def _expand_cross_references(
    chunks: list[PolicyChunk],
    chunks_by_id: dict[str, PolicyChunk],
) -> list[PolicyChunk]:
    """Add one-hop related-section chunks when tag intersection with originator is non-empty.

    Args:
        chunks: Initially retrieved chunks.
        chunks_by_id: Full index of all chunks for lookup.

    Returns:
        Expanded list with related chunks appended (no duplicates).
    """
    import re

    _RELATED_RE = re.compile(r"\*\*Related sections:\*\*\s*(.+)")

    seen_ids = {c.id for c in chunks}
    expanded = list(chunks)

    for chunk in chunks:
        m = _RELATED_RE.search(chunk.text)
        if not m:
            continue
        related_ids = [r.strip() for r in m.group(1).split(",")]
        for related_id in related_ids:
            if related_id in seen_ids:
                continue
            related = chunks_by_id.get(related_id)
            if related is None:
                continue
            if set(chunk.tags) & set(related.tags):
                expanded.append(related)
                seen_ids.add(related_id)

    return expanded


def retrieve(query: str, tracer) -> list[PolicyChunk]:
    """Module-level convenience shim used by the pipeline.

    Args:
        query: Natural language request.
        tracer: Pipeline tracer (unused until Slice 9 wiring).

    Returns:
        List of PolicyChunk objects.
    """
    raise NotImplementedError("Wire up a PolicyRetrieverBase instance at pipeline init time.")
