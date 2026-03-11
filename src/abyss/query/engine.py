# query/engine.py — RAG query engine
from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

from ..services.embedding_service import EmbeddingService
from ..storage.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


class QueryEngine:
    """
    RAG query engine.
    Search for the most relevant chunks in ChromaDB
    and return results with scores and metadata.

    Use ChromaStore directly (not LlamaIndex retriever)
    to support native ChromaDB where/where_document filters.
    """

    def __init__(self, store: ChromaStore, embed_model: Any | None = None):
        self._store = store
        # Stored for injection in tests; None = resolved lazily from EmbeddingService.
        self._embed_model_override = embed_model

    @cached_property
    def _embed_model(self) -> Any:
        """Shared model from EmbeddingService — loaded on first query call."""
        return self._embed_model_override or EmbeddingService.get_instance().get_embed_model()

    async def query(
        self,
        question: str,
        top_k: int = 6,
        where: dict | None = None,
        where_document: dict | None = None,
    ) -> dict:
        """
        Semantic search in indexed chunks.

        Args:
            question: Question in natural language
            top_k: Number of results to return
            where: ChromaDB filter on metadata
            where_document: ChromaDB filter on document text

        Returns:
            {
                "question": str,
                "chunks": [
                    {
                        "text": str,
                        "score": float,
                        "metadata": dict,
                    }
                ]
            }
        """
        # Check if there is data
        if self._store.count() == 0:
            return {
                "question": question,
                "chunks": [],
                "message": "No documents indexed. Use index_directory first.",
            }

        # Calculate the question embedding
        query_embedding = await self._embed_model.aget_text_embedding(question)

        # Execute the ChromaDB search
        try:
            results = self._store.query(
                query_embedding=query_embedding,
                n_results=top_k,
                where=where,
                where_document=where_document,
            )
        except Exception as e:
            logger.error("Error during ChromaDB query: %s", e)
            return {
                "question": question,
                "chunks": [],
                "error": str(e),
            }

        # Format the results
        chunks = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(documents)):
            doc_text = documents[i] if i < len(documents) else ""
            meta = metadatas[i] if i < len(metadatas) else {}
            distance = distances[i] if i < len(distances) else 1.0

            # ChromaDB cosine distance → similarity score (1 - distance)
            score = round(1.0 - distance, 4)

            chunks.append({
                "text": doc_text,
                "score": score,
                "metadata": {
                    k: v for k, v in (meta or {}).items()
                    if k not in ("_source_text",)  # exclure les champs internes
                },
            })

        result = {
            "question": question,
            "chunks": chunks,
        }
        logger.info(
            "Query: '%s' => %d results (top_k=%d)",
            question[:50], len(chunks), top_k,
        )
        return result
