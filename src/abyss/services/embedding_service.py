# services/embedding_service.py — Singleton service for the shared embedding model
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import ClassVar

from huggingface_hub import snapshot_download
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from ..config import EMBEDDING_CACHE_DIR, EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Singleton service that owns the shared embedding model instance.

    Responsibilities:
    - Download the model snapshot on first use via ``snapshot_download()``,
      storing it under ``EMBEDDING_CACHE_DIR``.
    - Reload from the local cache on subsequent starts (no outbound network call).
    - Expose a single ``HuggingFaceEmbedding`` instance shared by
      ``IngestionPipeline`` and ``QueryEngine``.
    """

    _instance: ClassVar[EmbeddingService | None] = None
    _embed_model: HuggingFaceEmbedding | None = None
    _snapshot_path: str | None = None

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        """Return the singleton instance, creating it if necessary."""
        if cls._instance is None:
            cls._instance = EmbeddingService()
        return cls._instance

    def get_embed_model(self) -> HuggingFaceEmbedding:
        """
        Return the shared ``HuggingFaceEmbedding`` instance.

        Triggers a download on first call if the model is not cached locally.
        Subsequent calls return the already-loaded instance immediately.
        """
        if self._embed_model is None:
            snapshot_path = self._ensure_snapshot()
            self._embed_model = HuggingFaceEmbedding(model_name=snapshot_path)
        return self._embed_model

    def get_max_seq_length(self) -> int:
        """
        Return the model's ``max_seq_length`` by reading
        ``sentence_bert_config.json`` from the local snapshot.

        No additional model load is required — just a small JSON file read.
        Falls back to 256 (the default for all-MiniLM-L6-v2) if the file
        is absent or malformed.
        """
        try:
            config_file = (
                Path(self._ensure_snapshot()) / "sentence_bert_config.json"
            )
            if config_file.exists():
                with config_file.open() as f:
                    return int(json.load(f).get("max_seq_length", 256))
        except Exception as exc:
            logger.warning(
                "Could not read max_seq_length from snapshot config: %s", exc
            )
        return 256

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_snapshot(self) -> str:
        """
        Ensure the model snapshot is available locally and return its path.

        ``snapshot_download()`` is a no-op when the snapshot is already present
        in ``EMBEDDING_CACHE_DIR``, so this method is safe to call repeatedly.
        """
        if self._snapshot_path is not None:
            return self._snapshot_path

        cache_dir = Path(EMBEDDING_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        model_id = EMBEDDING_MODEL_NAME

        # HuggingFace cache uses 'models--<owner>--<repo>' folder naming
        cache_subdir = cache_dir / ("models--" + model_id.replace("/", "--"))
        is_cached = cache_subdir.exists()

        if is_cached:
            logger.info(
                "Embedding model '%s' found in local cache (%s) — loading from cache.",
                model_id,
                cache_dir,
            )
        else:
            logger.info(
                "Embedding model '%s' not in local cache (%s) — download in progress.",
                model_id,
                cache_dir,
            )

        try:
            path = snapshot_download(
                repo_id=model_id,
                cache_dir=str(cache_dir),
                # Skip network entirely when the snapshot is already on disk.
                local_files_only=is_cached,
            )
        except Exception as exc:
            logger.error(
                "Failed to load embedding model '%s': %s",
                model_id,
                exc,
            )
            raise

        if is_cached:
            logger.info("Embedding model '%s' loaded from cache: %s", model_id, path)
        else:
            logger.info(
                "Embedding model '%s' downloaded and cached at: %s", model_id, path
            )

        self._snapshot_path = path
        return path
