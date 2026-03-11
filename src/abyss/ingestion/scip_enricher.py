# ingestion/scip_enricher.py — Enrichment of chunks with SCIP metadata
from __future__ import annotations

import logging
from pathlib import Path

from llama_index.core.schema import TextNode

from ..scip.scip_loader import ScipIndex
from .metadata import MetadataKeys

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  Module Constants (reduce duplication, improve maintainability)
# ──────────────────────────────────────────────────────────────────

# Glob pattern matching any SCIP index file:
#   index.scip, abyss.dotnet.index.scip, abyss.python.index.scip, etc.
SCIP_INDEX_GLOB = "*index.scip"

# Search strategy: max parent directories to walk up when no index found locally
MAX_PARENT_SEARCH_LEVELS = 3

# Metadata enrichment limits
MAX_RELATIONS = 10
"""Max number of callers/callees in metadata (ChromaDB has limits)"""

# Log prefix for SCIP-related messages
LOG_PREFIX_SCIP = "SCIP"

# Log message templates
LOG_MSG_NOT_FOUND = (
    f"No {LOG_PREFIX_SCIP} index files (*index.scip) found in or under %s"
    f" — {LOG_PREFIX_SCIP} enrichment disabled"
)
LOG_MSG_FOUND = f"Found %d {LOG_PREFIX_SCIP} index file(s): %s"
LOG_MSG_LOAD_ERROR = f"Error loading {LOG_PREFIX_SCIP} index at %s: %s — skipped"
LOG_MSG_ENRICHMENT_SUMMARY = (
    f"{LOG_PREFIX_SCIP}: %d / %d code chunks enriched"
    f" (total chunks: %d, indexes loaded: %d, total symbols: %d)"
)


class ScipEnricher:
    """
    Locate, load, and apply one or more SCIP indexes to enrich code chunks.

    All files matching ``*index.scip`` near the target directory are loaded;
    symbol lookup iterates through them in order (first match wins).

    Usage:
        enricher = ScipEnricher(directory)
        if enricher.available:
            count = enricher.enrich(nodes)
    """

    def __init__(self, directory: str | Path) -> None:
        """
        Locate and load all SCIP index files near *directory*.

        Lookup order:
        1. Files matching ``*index.scip`` directly in *directory*.
        2. Recursively inside subdirectories (rglob).
        3. Walking up to MAX_PARENT_SEARCH_LEVELS parent directories.

        Args:
            directory: Root path of the source being ingested.
        """
        self._scip_indexes: list[ScipIndex] = []
        directory = Path(directory).resolve()
        scip_paths = self._find_scip_files(directory)

        if not scip_paths:
            logger.warning(LOG_MSG_NOT_FOUND, directory)
            return

        logger.info(LOG_MSG_FOUND, len(scip_paths), ", ".join(str(p) for p in scip_paths))
        for path in scip_paths:
            try:
                self._scip_indexes.append(ScipIndex(path))
            except Exception as e:
                logger.error(LOG_MSG_LOAD_ERROR, path, e)

    @property
    def available(self) -> bool:
        """True when at least one SCIP index was successfully loaded."""
        return len(self._scip_indexes) > 0

    def enrich(self, nodes: list[TextNode]) -> int:
        """
        Enrich code TextNode chunks with SCIP metadata (in-place).

        For each code chunk:
        1. Extract file_path and start_line / end_line from existing metadata.
        2. Search all loaded indexes for the corresponding symbol (first match wins).
        3. Inject: symbol, display_name, kind, documentation, callers, callees.

        Args:
            nodes: List of TextNode produced by the parsers.

        Returns:
            Number of chunks that were successfully enriched.
        """
        if not self._scip_indexes:
            return 0

        enriched_count = 0
        code_count = 0
        total_symbols = sum(len(idx.symbols) for idx in self._scip_indexes)

        for node in nodes:
            if node.metadata.get(MetadataKeys.CHUNK_TYPE) != MetadataKeys.CHUNK_TYPE_CODE:
                continue

            code_count += 1
            file_path  = node.metadata.get(MetadataKeys.FILE_PATH, "")
            start_line = node.metadata.get(MetadataKeys.START_LINE, 0)
            end_line   = node.metadata.get(MetadataKeys.END_LINE, 0)

            sym = self._lookup_symbol(file_path, start_line, end_line)
            if sym is None:
                continue

            node.metadata[MetadataKeys.SYMBOL]       = sym.symbol
            node.metadata[MetadataKeys.DISPLAY_NAME]  = sym.display_name
            node.metadata[MetadataKeys.KIND]          = sym.kind
            node.metadata[MetadataKeys.ENCLOSING]     = sym.enclosing or ""

            if sym.documentation:
                node.metadata[MetadataKeys.DOCUMENTATION] = "\n".join(sym.documentation)

            # Callers / callees — serialized as string for ChromaDB
            # (ChromaDB does not support lists in metadata)
            if sym.callers:
                node.metadata[MetadataKeys.CALLERS] = ", ".join(sym.callers[:MAX_RELATIONS])
            if sym.callees:
                node.metadata[MetadataKeys.CALLEES] = ", ".join(sym.callees[:MAX_RELATIONS])

            enriched_count += 1

        logger.info(
            LOG_MSG_ENRICHMENT_SUMMARY,
            enriched_count, code_count, len(nodes),
            len(self._scip_indexes), total_symbols,
        )
        return enriched_count

    # ── Private helpers ─────────────────────────────────────────

    def _lookup_symbol(self, file_path: str, start_line: int, end_line: int):
        """Search all loaded indexes for a symbol; return first match or None."""
        for idx in self._scip_indexes:
            sym = idx.get_by_file_line(file_path, start_line, end_line)
            if sym is not None:
                return sym
        return None

    @staticmethod
    def _find_scip_files(directory: Path) -> list[Path]:
        """
        Search for all files matching SCIP_INDEX_GLOB (``*index.scip``):
        1. Directly in *directory* (non-recursive glob).
        2. Recursively in subdirectories (rglob), if step 1 found nothing.
        3. Walking up parent directories (up to MAX_PARENT_SEARCH_LEVELS),
           if steps 1–2 found nothing.

        Returns a deduplicated, sorted list of matching paths.
        """
        found: set[Path] = set()

        # 1. Direct (non-recursive) search in the directory itself
        found.update(directory.glob(SCIP_INDEX_GLOB))
        if found:
            return sorted(found)

        # 2. Recursive search in subdirectories
        try:
            found.update(directory.rglob(SCIP_INDEX_GLOB))
        except OSError:
            pass
        if found:
            return sorted(found)

        # 3. Walk up parent directories (up to MAX_PARENT_SEARCH_LEVELS)
        current = directory.parent
        for _ in range(MAX_PARENT_SEARCH_LEVELS):
            if not current or current == current.parent:
                break
            found.update(current.glob(SCIP_INDEX_GLOB))
            if found:
                return sorted(found)
            current = current.parent

        return []
