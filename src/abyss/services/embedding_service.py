# services/embedding_service.py — Singleton service for the shared embedding model
# RQ-OLL-001, RQ-OLL-007, DEC-OLL-001, DEC-OLL-004
from __future__ import annotations

import logging
from typing import ClassVar

from llama_index.embeddings.ollama import OllamaEmbedding

from ..config import OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Singleton service that owns the shared OllamaEmbedding instance.

    Responsibilities:
    - Build an OllamaEmbedding client pointed at OLLAMA_BASE_URL on first use.
    - Expose a single OllamaEmbedding instance shared by
      IngestionPipeline and QueryEngine.
    - No in-process model loading; all embedding computation is delegated
      to the local Ollama server via HTTP (RQ-OLL-001, RQ-OLL-006).

    Error behaviour (RQ-OLL-007):
    - If the Ollama server is unreachable, OllamaEmbedding raises an
      exception on the first actual embedding call. The exception propagates
      to the caller; this service does not swallow it silently.
    """

    _instance: ClassVar[EmbeddingService | None] = None
    _embed_model: OllamaEmbedding | None = None

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        """Return the singleton instance, creating it if necessary."""
        if cls._instance is None:
            cls._instance = EmbeddingService()
        return cls._instance

    def get_embed_model(self) -> OllamaEmbedding:
        """
        Return the shared OllamaEmbedding instance.

        Builds the client on first call using OLLAMA_BASE_URL and
        OLLAMA_EMBEDDING_MODEL from config. Subsequent calls return the
        already-created instance immediately — no network call is made here.
        """
        if self._embed_model is None:
            logger.info(
                "Initialising OllamaEmbedding: model='%s' base_url='%s'",
                OLLAMA_EMBEDDING_MODEL,
                OLLAMA_BASE_URL,
            )
            self._embed_model = OllamaEmbedding(
                model_name=OLLAMA_EMBEDDING_MODEL,
                base_url=OLLAMA_BASE_URL,
            )
        return self._embed_model
