# tests/test_batch_ingestion.py
# Unit tests for batch directory ingestion
# RQ-BIN-001, RQ-BIN-002, RQ-BIN-003, RQ-BIN-004, RQ-BIN-005, RQ-BIN-006, RQ-BIN-007
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_temp_files(directory: str, count: int, ext: str = ".py") -> list[Path]:
    """Create `count` minimal source files in `directory`."""
    paths = []
    for i in range(count):
        p = Path(directory) / f"file_{i}{ext}"
        p.write_text(f"# file {i}\ndef func_{i}(): pass\n", encoding="utf-8")
        paths.append(p)
    return paths


def _make_pipeline(tmp_dir: str):
    """Return an IngestionPipeline with mocked store, registry, and embed model."""
    from abyss.ingestion.ingestion_pipeline import IngestionPipeline
    from abyss.storage.chroma_store import ChromaStore
    from abyss.storage.document_registry import DocumentRegistry

    store = MagicMock(spec=ChromaStore)
    store.delete_by_file = MagicMock(return_value=0)
    store.add_chunks = MagicMock()

    registry = MagicMock(spec=DocumentRegistry)
    registry.exists = MagicMock(return_value=False)
    registry.register = MagicMock()

    embed_model = MagicMock()
    embed_model.aget_text_embedding_batch = AsyncMock(return_value=[[0.1] * 4])

    pipeline = IngestionPipeline(store=store, registry=registry, embed_model=embed_model)
    return pipeline, store, registry


# ══════════════════════════════════════════════════════════════════════════════
#  RQ-BIN-004 — Config defaults
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchIngestionConfigDefaults:
    """
    Given: config.py loaded with no config.yaml overrides
    When:  INGEST_BATCH_SIZE and INGEST_LARGE_DIR_THRESHOLD are read
    Then:  they equal the expected built-in defaults
    """

    def test_ingest_batch_size_default(self):
        # RQ-BIN-004, DEC-BIN-004
        from abyss.config import INGEST_BATCH_SIZE
        assert INGEST_BATCH_SIZE == 100

    def test_ingest_large_dir_threshold_default(self):
        # RQ-BIN-004, DEC-BIN-004
        from abyss.config import INGEST_LARGE_DIR_THRESHOLD
        assert INGEST_LARGE_DIR_THRESHOLD == 10_000


# ══════════════════════════════════════════════════════════════════════════════
#  RQ-BIN-001, RQ-BIN-007 — Single batch (small directory)
# ══════════════════════════════════════════════════════════════════════════════

class TestSingleBatchSmallDirectory:
    """
    Given: a directory with fewer files than INGEST_BATCH_SIZE
    When:  ingest_directory is called
    Then:  all files are processed in a single batch (RQ-BIN-007 no regression)
    """

    @pytest.mark.asyncio
    async def test_small_dir_produces_one_batch(self):
        # RQ-BIN-001, RQ-BIN-007
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=3)
            pipeline, _, _ = _make_pipeline(tmp)

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=100,
            )

            assert result["status"] == "ok"
            assert result["files_processed"] == 3
            assert len(result["batches"]) == 1
            assert result["batches"][0]["files_processed"] == 3
            assert result["batches_completed"] == 1
            assert result["batches_failed"] == 0

    @pytest.mark.asyncio
    async def test_empty_dir_returns_ok_zero_files(self):
        # RQ-BIN-007 — no regression: empty dir must still succeed
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, _, _ = _make_pipeline(tmp)

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=100,
            )

            assert result["status"] == "ok"
            assert result["files_processed"] == 0
            assert result["batches"] == []
            assert result["batches_completed"] == 0
            assert result["batches_failed"] == 0


# ══════════════════════════════════════════════════════════════════════════════
#  RQ-BIN-001, RQ-BIN-005 — Multi-batch (large directory)
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiBatchLargeDirectory:
    """
    Given: a directory with more files than batch_size
    When:  ingest_directory is called
    Then:  files are processed in multiple sequential batches
    And:   the response contains per-batch stats (RQ-BIN-005)
    """

    @pytest.mark.asyncio
    async def test_250_files_produces_three_batches(self):
        # RQ-BIN-001, RQ-BIN-005: 250 files / batch=100 -> 3 batches (100+100+50)
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=250)
            pipeline, _, _ = _make_pipeline(tmp)

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=100,
            )

            assert result["status"] == "ok"
            assert result["files_processed"] == 250
            assert len(result["batches"]) == 3
            assert result["batches"][0]["files_processed"] == 100
            assert result["batches"][1]["files_processed"] == 100
            assert result["batches"][2]["files_processed"] == 50
            assert result["batches_completed"] == 3
            assert result["batches_failed"] == 0

    @pytest.mark.asyncio
    async def test_batch_result_contains_required_fields(self):
        # RQ-BIN-005 — each batch element has required keys
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=5)
            pipeline, _, _ = _make_pipeline(tmp)

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=100,
            )

            assert len(result["batches"]) == 1
            batch = result["batches"][0]
            assert "batch_index" in batch
            assert "files_processed" in batch
            assert "chunks_created" in batch
            assert "errors" in batch

    @pytest.mark.asyncio
    async def test_total_chunks_equals_sum_of_batch_chunks(self):
        # RQ-BIN-005 — totals match sum of per-batch values
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=10)
            pipeline, _, _ = _make_pipeline(tmp)

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=4,
            )

            total_from_batches = sum(b["chunks_created"] for b in result["batches"])
            assert result["chunks_created"] == total_from_batches


# ══════════════════════════════════════════════════════════════════════════════
#  RQ-BIN-006 — Stop-on-batch-failure
# ══════════════════════════════════════════════════════════════════════════════

class TestStopOnBatchFailure:
    """
    Given: a batch raises an unhandled exception
    When:  ingest_directory is called
    Then:  processing stops immediately
    And:   status is "partial"
    And:   batches_completed and batches_failed counters are accurate
    """

    @pytest.mark.asyncio
    async def test_second_batch_failure_stops_processing(self):
        # RQ-BIN-006, DEC-BIN-003
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=25)
            pipeline, store, _ = _make_pipeline(tmp)

            # Fail on the second call to _embed_and_store (second batch)
            call_count = {"n": 0}
            original = pipeline._embed_and_store

            async def failing_embed_and_store(nodes):
                call_count["n"] += 1
                if call_count["n"] == 2:
                    raise RuntimeError("Simulated embedding failure")
                await original(nodes)

            pipeline._embed_and_store = failing_embed_and_store

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=10,
            )

            assert result["status"] == "partial"
            assert result["batches_completed"] == 1
            assert result["batches_failed"] == 1
            # Only 3 batches were expected (25 files / 10), but 3rd was never started
            assert len(result["batches"]) == 2

    @pytest.mark.asyncio
    async def test_first_batch_failure_yields_zero_completed(self):
        # RQ-BIN-006 — if batch 0 fails, batches_completed == 0
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=5)
            pipeline, _, _ = _make_pipeline(tmp)

            async def always_fail(nodes):
                raise RuntimeError("immediate failure")

            pipeline._embed_and_store = always_fail

            result = await pipeline.ingest_directory(
                directory=tmp,
                extensions={".py"},
                batch_size=100,
            )

            assert result["status"] == "partial"
            assert result["batches_completed"] == 0
            assert result["batches_failed"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  RQ-BIN-002, RQ-BIN-003 — Large-directory gate (_count_matching_files)
# ══════════════════════════════════════════════════════════════════════════════

class TestCountMatchingFiles:
    """
    Given: a directory with a known file count
    When:  _count_matching_files is called
    Then:  it returns the correct count (no parsing performed)
    """

    def test_counts_matching_extensions_only(self):
        # RQ-BIN-002, DEC-BIN-002
        from abyss.server import _count_matching_files
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=5, ext=".py")
            _make_temp_files(tmp, count=3, ext=".cs")

            count_py = _count_matching_files(tmp, {".py"}, [])
            count_cs = _count_matching_files(tmp, {".cs"}, [])
            count_both = _count_matching_files(tmp, {".py", ".cs"}, [])

            assert count_py == 5
            assert count_cs == 3
            assert count_both == 8

    def test_respects_exclude_dirs(self):
        # RQ-BIN-002, DEC-BIN-002 -- excluded dirs must not be counted
        from abyss.server import _count_matching_files
        with tempfile.TemporaryDirectory() as tmp:
            _make_temp_files(tmp, count=3, ext=".py")
            subdir = Path(tmp) / "node_modules"
            subdir.mkdir()
            _make_temp_files(str(subdir), count=5, ext=".py")

            count = _count_matching_files(tmp, {".py"}, ["node_modules"])
            assert count == 3

    def test_nonexistent_directory_returns_zero(self):
        # RQ-BIN-002 -- graceful handling of bad path
        from abyss.server import _count_matching_files
        count = _count_matching_files("/nonexistent/path/xyz", {".py"}, [])
        assert count == 0
