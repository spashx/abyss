# ingestion/pipeline.py — Ingestion pipeline orchestrator
from __future__ import annotations

import time
import uuid
import logging
from collections import defaultdict
from functools import cached_property
from pathlib import Path
from typing import Any

from llama_index.core.schema import TextNode

from ..config import CHUNK_OVERLAP, CHUNK_SIZE, EXCLUDE_EXTENSIONS
from ..services.embedding_service import EmbeddingService
from ..storage.chroma_store import ChromaStore
from ..storage.document_registry import DocumentRegistry
from .embed_builder import EmbedBuilder
from .file_discovery import FileDiscovery, FileType
from .scip_enricher import ScipEnricher
from .parsers.code_parser import CodeParser
from .parsers.doc_parser import DocumentParser
from .parsers.json_parser import JsonParser
from .parsers.xml_parser import XmlParser

logger = logging.getLogger(__name__)

# ── Stats label keys — single source of truth ─────────────────────────────────
_STAT_CODE     = FileType.CODE.value      # "code"
_STAT_DOCUMENT = FileType.DOCUMENT.value  # "document"
_STAT_UNKNOWN  = FileType.UNKNOWN.value   # "unknown"
_STAT_JSON     = "json"
_STAT_XML      = "xml"
_EXT_JSON      = ".json"

# Ordered tuple used to initialize and iterate parser counters consistently
_PARSER_COUNTER_KEYS: tuple[str, ...] = (
    _STAT_CODE, _STAT_DOCUMENT, _STAT_JSON, _STAT_XML, _STAT_UNKNOWN
)


def _log_ingestion_summary(
    log: logging.Logger,
    total_files: int,
    elapsed: float,
    files_per_sec: float,
    by_parser: dict[str, int],
    by_language: dict[str, int],
) -> None:
    """
    Log a human-readable ingestion statistics summary at INFO level.

    Args:
        log:          Logger to write to.
        total_files:  Total number of successfully ingested files.
        elapsed:      Wall-clock duration in seconds.
        files_per_sec: Average ingestion speed.
        by_parser:    Counts per parser type (code, document, json, xml, unknown).
        by_language:  Counts per tree-sitter language (code files only).
    """
    log.info(
        "Ingestion complete: %d files in %.2fs (%.2f files/sec)",
        total_files, elapsed, files_per_sec,
    )
    for parser_type, count in by_parser.items():
        if count == 0:
            continue
        if parser_type == _STAT_CODE and by_language:
            lang_detail = ", ".join(
                f"{lang}: {n}"
                for lang, n in sorted(by_language.items(), key=lambda x: -x[1])
            )
            log.info("  %-10s: %d files  (%s)", parser_type, count, lang_detail)
        else:
            log.info("  %-10s: %d file%s", parser_type, count, "s" if count != 1 else "")


class IngestionPipeline:
    """
    Orchestrate the complete ingestion pipeline:
    1. File discovery    (FileDiscovery)
    2. Parsing by type   (CodeParser / JsonParser / XmlParser / DocumentParser)
    3. SCIP enrichment   (ScipEnricher — optional)
    4. Embed text build  (EmbedBuilder — semantic header)
    5. Embedding         (OllamaEmbedding via Ollama server)
    6. Storage           (ChromaStore)
    7. Registration      (DocumentRegistry)
    """

    def __init__(
        self,
        store: ChromaStore,
        registry: DocumentRegistry,
        embed_model: Any | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        # Stored for injection in tests; None = resolved lazily from EmbeddingService.
        self._embed_model_override = embed_model

    # ── Lazy-loaded collaborators (created only on first actual use) ──────────

    @cached_property
    def _embed_model(self) -> Any:
        return self._embed_model_override or EmbeddingService.get_instance().get_embed_model()

    @cached_property
    def _chunk_params(self) -> tuple[int, int]:
        # RQ-OLL-004, DEC-OLL-003 -- chunk size read from config, not inferred from model
        logger.info(
            "Chunk params from config: chunk_size=%d, chunk_overlap=%d",
            CHUNK_SIZE, CHUNK_OVERLAP,
        )
        return CHUNK_SIZE, CHUNK_OVERLAP

    @cached_property
    def _discovery(self) -> FileDiscovery:
        return FileDiscovery(exclude_extensions=EXCLUDE_EXTENSIONS)

    @cached_property
    def _code_parser(self) -> CodeParser:
        return CodeParser(*self._chunk_params)

    @cached_property
    def _json_parser(self) -> JsonParser:
        return JsonParser(*self._chunk_params)

    @cached_property
    def _xml_parser(self) -> XmlParser:
        return XmlParser(*self._chunk_params)

    @cached_property
    def _document_parser(self) -> DocumentParser:
        return DocumentParser(*self._chunk_params)

    @cached_property
    def _embed_builder(self) -> EmbedBuilder:
        return EmbedBuilder()

    # ── Indexing of a complete directory ───────────────────────────

    async def ingest_directory(
        self,
        directory: str,
        extensions: set[str] | None = None,
        exclude_dirs: list[str] | None = None,
        exclude_extensions: set[str] | None = None,
    ) -> dict:
        """
        Main entry point — index every supported file in a directory tree.

        Args:
            directory:          Root directory to scan.
            extensions:         Extensions to include (default: all supported).
            exclude_dirs:       Directory names to skip (default: DEFAULT_EXCLUDE_DIRS).
            exclude_extensions: Extensions to exclude explicitly (default: EXCLUDE_EXTENSIONS).

        Returns:
            {
                "status": "ok",
                "files_processed": int,
                "chunks_created": int,
                "scip_enriched": int,
                "errors": list[str],
            }
        """
        directory_path = Path(directory).resolve()
        start_time = time.perf_counter()

        # Stats counters — keys driven by _PARSER_COUNTER_KEYS (no literals here)
        by_parser: dict[str, int] = dict.fromkeys(_PARSER_COUNTER_KEYS, 0)
        by_language: dict[str, int] = defaultdict(int)

        # 1. Discover files
        discovery = FileDiscovery(
            extensions=extensions,
            exclude_dirs=exclude_dirs,
            exclude_extensions=exclude_extensions if exclude_extensions is not None else EXCLUDE_EXTENSIONS,
        )
        files = discovery.discover(directory_path)

        # 2. SCIP enricher (loads index once for the whole directory)
        scip_enricher = ScipEnricher(directory_path)

        # 3. Parse each file
        all_nodes: list[TextNode] = []
        file_nodes_map: dict[str, list[TextNode]] = {}
        errors: list[str] = []

        for file_path in files:
            try:
                if self._registry.exists(str(file_path)):
                    self._store.delete_by_file(str(file_path))
                nodes = self._parse_file(file_path)
                all_nodes.extend(nodes)
                file_nodes_map[str(file_path)] = nodes

                # Track parser type for statistics
                label = self._parser_label(file_path)
                by_parser[label] += 1
                if label == _STAT_CODE:
                    lang = self._discovery.get_language(file_path) or file_path.suffix.lower().lstrip(".")
                    by_language[lang] += 1
            except Exception as e:
                msg = f"Error on {file_path}: {e}"
                logger.error(msg)
                errors.append(msg)

        # 4. SCIP enrichment
        scip_count = scip_enricher.enrich(all_nodes) if scip_enricher.available else 0

        # 5. Build embedded text (semantic header + content)
        self._embed_builder.apply(all_nodes)

        # 6. Embedding + storage
        await self._embed_and_store(all_nodes)

        # 7. Register each file in the registry
        for file_path_str, nodes in file_nodes_map.items():
            fp = Path(file_path_str)
            try:
                size = fp.stat().st_size
            except OSError:
                size = 0
            self._registry.register(
                file_path=file_path_str,
                chunk_count=len(nodes),
                file_size=size,
            )

        elapsed = time.perf_counter() - start_time
        total_files = len(file_nodes_map)
        files_per_sec = round(total_files / elapsed, 2) if elapsed > 0 else 0.0

        ingestion_stats = {
            "elapsed_seconds": round(elapsed, 2),
            "files_per_second": files_per_sec,
            "by_parser": dict(by_parser),
            "by_language": dict(by_language),
        }

        _log_ingestion_summary(
            logger, total_files, elapsed, files_per_sec, by_parser, dict(by_language)
        )

        result = {
            "status": "ok",
            "files_processed": total_files,
            "chunks_created": len(all_nodes),
            "scip_enriched": scip_count,
            "errors": errors,
            "ingestion_stats": ingestion_stats,
        }
        logger.info("Ingestion completed: %s", result)
        return result

    # ── Indexing a single file ────────────────────────────

    async def ingest_single_file(self, file_path: str) -> dict:
        """
        Index a single file. Used by replace_document.

        Args:
            file_path: Absolute path to the file.

        Returns:
            {"status": "ok", "chunks_created": int, "scip_enriched": int}
            or {"status": "error", "message": str}
        """
        fp = Path(file_path).resolve()
        if not fp.is_file():
            return {"status": "error", "message": f"File not found: {fp}"}

        try:
            nodes = self._parse_file(fp)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        # SCIP: load from the parent directory
        scip_enricher = ScipEnricher(fp.parent)
        scip_count = scip_enricher.enrich(nodes) if scip_enricher.available else 0

        self._embed_builder.apply(nodes)
        await self._embed_and_store(nodes)

        try:
            size = fp.stat().st_size
        except OSError:
            size = 0
        self._registry.register(
            file_path=str(fp),
            chunk_count=len(nodes),
            file_size=size,
        )

        return {
            "status": "ok",
            "chunks_created": len(nodes),
            "scip_enriched": scip_count,
        }

    # ── Parsing a file by type ───────────────────────

    def _parser_label(self, file_path: Path) -> str:
        """
        Return the stats label for a file's parser category.

        Single source of truth for the mapping FileType -> stats key,
        used by both ingest_directory (counters) and _log_ingestion_summary.
        """
        file_type = self._discovery.classify(file_path)
        if file_type == FileType.CODE:
            return _STAT_CODE
        if file_type == FileType.DOCUMENT:
            return _STAT_DOCUMENT
        if file_type == FileType.STRUCTURED:
            return _STAT_JSON if file_path.suffix.lower() == _EXT_JSON else _STAT_XML
        return _STAT_UNKNOWN

    def _parse_file(self, file_path: Path) -> list[TextNode]:
        """
        Dispatch to the appropriate parser based on FileDiscovery.classify().
        """
        file_type = self._discovery.classify(file_path)

        if file_type == FileType.CODE:
            return self._code_parser.parse(file_path)
        elif file_type == FileType.STRUCTURED:
            ext = file_path.suffix.lower()
            if ext == ".json":
                return self._json_parser.parse(file_path)
            else:
                return self._xml_parser.parse(file_path)
        elif file_type == FileType.DOCUMENT:
            return self._document_parser.parse(file_path)
        else:
            logger.info("Unknown type for %s — fallback to text", file_path)
            return self._document_parser.parse_fallback(file_path)

    # ── Embedding + storage in ChromaDB ────────────────────────

    async def _embed_and_store(self, nodes: list[TextNode]) -> None:
        """
        Compute embeddings in batches and store chunks in ChromaDB.
        Batching avoids timeouts on large directories.
        """
        if not nodes:
            return

        BATCH_SIZE = 50

        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i : i + BATCH_SIZE]
            texts = [node.text for node in batch]
            embeddings = await self._embed_model.aget_text_embedding_batch(texts)
            ids = [self._make_chunk_id(node) for node in batch]
            metadatas = [self._sanitize_metadata(node.metadata) for node in batch]

            self._store.add_chunks(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
                embeddings=embeddings,
            )

        logger.info("Stored %d chunks in ChromaDB", len(nodes))

    # ── Utilities ───────────────────────────────────────────────

    @staticmethod
    def _make_chunk_id(node: TextNode) -> str:
        """Generate a guaranteed unique ID for a chunk using UUID4."""
        return str(uuid.uuid4())

    @staticmethod
    def _sanitize_metadata(meta: dict) -> dict:
        """
        Convert metadata values to scalar types accepted by ChromaDB
        (str, int, float, bool only).
        """
        sanitized = {}
        for key, value in meta.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, list):
                sanitized[key] = ", ".join(str(v) for v in value)
            elif value is None:
                sanitized[key] = ""
            else:
                sanitized[key] = str(value)
        return sanitized
