# storage/document_registry.py — Registry of indexed documents
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_NAME = "document-registry"


class DocumentRegistry:
    """
    Registry of indexed documents.

    Stored in a separate ChromaDB collection '_document_registry'.
    Each indexed document has an entry with:
    - file_path (unique ID based on SHA256 of the path)
    - file_name
    - indexed_at (ISO timestamp)
    - file_size (bytes)
    - chunk_count
    - file_hash (SHA256 of content)
    """

    def __init__(self, client: chromadb.ClientAPI):
        self._collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
        )

    def register(
        self,
        file_path: str,
        chunk_count: int,
        file_size: int = 0,
    ) -> None:
        """
        Register or update a document in the registry.
        """
        doc_id = self._make_id(file_path)
        file_hash = self._hash_file(file_path)

        metadata = {
            "file_path": file_path,
            "file_name": Path(file_path).name,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "file_size": file_size,
            "chunk_count": chunk_count,
            "file_hash": file_hash,
        }

        self._collection.upsert(
            ids=[doc_id],
            documents=[file_path],
            metadatas=[metadata],
        )
        logger.debug("Registry: registered %s (%d chunks)", file_path, chunk_count)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all entries from the registry."""
        results = self._collection.get(include=["metadatas"])
        return results.get("metadatas") or []

    def unregister(self, file_path: str) -> None:
        """Remove a document from the registry."""
        doc_id = self._make_id(file_path)
        try:
            self._collection.delete(ids=[doc_id])
            logger.debug("Registry: deleted %s", file_path)
        except Exception:
            logger.warning("Registry: %s not found for deletion", file_path)

    def exists(self, file_path: str) -> bool:
        """Check if a document is in the registry."""
        doc_id = self._make_id(file_path)
        results = self._collection.get(ids=[doc_id], include=[])
        return bool(results.get("ids"))

    def clear(self) -> None:
        """Completely clear the registry."""
        # Get all IDs and delete them
        results = self._collection.get(include=[])
        ids = results.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        logger.info("Registry cleared (%d entries deleted)", len(ids))

    @staticmethod
    def _make_id(file_path: str) -> str:
        """Generate a deterministic ID based on the file path."""
        return hashlib.sha256(file_path.encode()).hexdigest()

    @staticmethod
    def _hash_file(file_path: str) -> str:
        """Compute the SHA256 of the file content."""
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()[:16]
        except OSError:
            return ""
