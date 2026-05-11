"""Embeddings: ChromaDB client and collection management for policy chunks."""

import chromadb
from chromadb.utils import embedding_functions


def get_collection(name: str = "policy") -> chromadb.Collection:
    """Return an ephemeral ChromaDB collection with cosine-similarity and default embeddings.

    Args:
        name: Collection name.

    Returns:
        An empty ChromaDB Collection ready for document ingestion.
    """
    client = chromadb.EphemeralClient()
    ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(
        name=name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
