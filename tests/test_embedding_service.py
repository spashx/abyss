# tests/test_embedding_service.py
# Unit tests for EmbeddingService Ollama migration
# RQ-OLL-001, RQ-OLL-007, DEC-OLL-001, DEC-OLL-004
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestEmbeddingServiceSingleton:
    """
    Given: EmbeddingService singleton pattern
    When:  get_instance() is called multiple times
    Then:  the same instance is returned each time
    """

    def setup_method(self):
        # Reset singleton state between tests
        from abyss.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._embed_model = None

    def test_get_instance_returns_same_object(self):
        from abyss.services.embedding_service import EmbeddingService
        a = EmbeddingService.get_instance()
        b = EmbeddingService.get_instance()
        assert a is b

    def test_get_instance_returns_embedding_service(self):
        from abyss.services.embedding_service import EmbeddingService
        instance = EmbeddingService.get_instance()
        assert isinstance(instance, EmbeddingService)


class TestGetEmbedModel:
    """
    Given: EmbeddingService backed by OllamaEmbedding (RQ-OLL-001, DEC-OLL-001)
    When:  get_embed_model() is called
    Then:  an OllamaEmbedding built with OLLAMA_BASE_URL and OLLAMA_EMBEDDING_MODEL is returned
    """

    def setup_method(self):
        from abyss.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._embed_model = None

    def test_get_embed_model_returns_ollama_embedding(self):
        # Given: OllamaEmbedding is mocked
        mock_embed = MagicMock()
        with patch(
            "abyss.services.embedding_service.OllamaEmbedding",
            return_value=mock_embed,
        ) as mock_cls:
            from abyss.services.embedding_service import EmbeddingService
            from abyss.config import OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL

            svc = EmbeddingService.get_instance()
            model = svc.get_embed_model()

            # Then: OllamaEmbedding was constructed with the correct params
            mock_cls.assert_called_once_with(
                model_name=OLLAMA_EMBEDDING_MODEL,
                base_url=OLLAMA_BASE_URL,
            )
            assert model is mock_embed

    def test_get_embed_model_cached_on_second_call(self):
        # Given: OllamaEmbedding is mocked
        mock_embed = MagicMock()
        with patch(
            "abyss.services.embedding_service.OllamaEmbedding",
            return_value=mock_embed,
        ) as mock_cls:
            from abyss.services.embedding_service import EmbeddingService

            svc = EmbeddingService.get_instance()
            first = svc.get_embed_model()
            second = svc.get_embed_model()

            # Then: OllamaEmbedding constructor called only once
            mock_cls.assert_called_once()
            assert first is second

    def test_no_huggingface_import(self):
        # Then: huggingface_hub and HuggingFaceEmbedding are not imported (RQ-OLL-005)
        import sys
        assert "huggingface_hub" not in sys.modules
        assert "llama_index.embeddings.huggingface" not in sys.modules


class TestConfigOllamaDefaults:
    """
    Given: config.yaml does not override Ollama settings (RQ-OLL-002, RQ-OLL-003, RQ-OLL-004)
    When:  config module is imported
    Then:  default constants have the expected values
    """

    def test_ollama_base_url_default(self):
        from abyss.config import OLLAMA_BASE_URL
        assert OLLAMA_BASE_URL == "http://localhost:11434"

    def test_ollama_embedding_model_default(self):
        from abyss.config import OLLAMA_EMBEDDING_MODEL
        assert OLLAMA_EMBEDDING_MODEL == "nomic-embed-text"

    def test_chunk_size_is_positive_int(self):
        from abyss.config import CHUNK_SIZE
        assert isinstance(CHUNK_SIZE, int)
        assert CHUNK_SIZE > 0

    def test_chunk_overlap_derived_from_ratio(self):
        from abyss.config import CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_OVERLAP_RATIO
        assert CHUNK_OVERLAP == round(CHUNK_SIZE * CHUNK_OVERLAP_RATIO)

    def test_hf_constants_removed(self):
        # RQ-OLL-005: old HuggingFace config constants must not exist
        import abyss.config as cfg
        assert not hasattr(cfg, "EMBEDDING_MODEL_NAME")
        assert not hasattr(cfg, "EMBEDDING_CACHE_DIR")


class TestIngestionPipelineChunkParams:
    """
    Given: CHUNK_SIZE and CHUNK_OVERLAP from config (RQ-OLL-004, DEC-OLL-003)
    When:  IngestionPipeline._chunk_params is accessed
    Then:  it returns (CHUNK_SIZE, CHUNK_OVERLAP) without calling any model
    """

    def test_chunk_params_from_config(self):
        from abyss.config import CHUNK_SIZE, CHUNK_OVERLAP
        from abyss.ingestion.ingestion_pipeline import IngestionPipeline
        from unittest.mock import MagicMock

        store = MagicMock()
        registry = MagicMock()
        pipeline = IngestionPipeline(store, registry)

        # When: _chunk_params is accessed
        params = pipeline._chunk_params

        # Then: returns (CHUNK_SIZE, CHUNK_OVERLAP)
        assert params == (CHUNK_SIZE, CHUNK_OVERLAP)

    def test_infer_chunk_params_removed(self):
        # RQ-OLL-005: _infer_chunk_params must not exist in the module
        import abyss.ingestion.ingestion_pipeline as m
        assert not hasattr(m, "_infer_chunk_params")
