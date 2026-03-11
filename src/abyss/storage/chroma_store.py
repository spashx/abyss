# storage/chroma_store.py — ChromaDB interface for vector storage
from __future__ import annotations

import logging
from typing import Any

import chromadb

from ..config import CHROMA_PERSIST_DIR
from ..ingestion.metadata import MetadataKeys

logger = logging.getLogger(__name__)

COLLECTION_NAME = "chunks"


class ChromaStore:
    """
    Interface to ChromaDB for chunk storage and search.

    Uses a PersistentClient (SQLite) and a single 'chunks' collection
    with cosine metric (adapted for sentence-transformers embeddings).
    """

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaStore initialized (persist_dir=%s, collection=%s, count=%d)",
            persist_dir, COLLECTION_NAME, self.collection.count(),
        )

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """Add chunks with their embeddings and metadata."""
        if not ids:
            return
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def delete_by_file(self, file_path: str) -> int:
        """
        Delete all chunks associated with a file.
        Return the number of deleted chunks.
        """
        # Get the IDs of the chunks for this file
        results = self.collection.get(
            where={MetadataKeys.FILE_PATH: file_path},
            include=[],
        )
        ids = results.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
        logger.info("delete_by_file(%s): %d chunks deleted", file_path, len(ids))
        return len(ids)

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict | None = None,
        where_document: dict | None = None,
    ) -> dict:
        """
        Search for closest chunks by cosine similarity.

        Args:
            query_embedding: Query vector
            n_results: Number of results
            where: ChromaDB filter on metadata
            where_document: ChromaDB filter on document text

        Returns:
            ChromaDB results (ids, documents, metadatas, distances)
        """
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            kwargs["where"] = where
        if where_document is not None:
            kwargs["where_document"] = where_document

        return self.collection.query(**kwargs)

    def clear_all(self) -> None:
        """Delete all chunks from the collection."""
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaStore: collection '%s' cleared", COLLECTION_NAME)

    def count(self) -> int:
        """Return the total number of chunks."""
        return self.collection.count()
