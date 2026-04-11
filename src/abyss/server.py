# server.py — Complete MCP Server with 8 tools + 3 resources
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool

from .config import (
    ALL_SUPPORTED_EXTENSIONS,
    CHROMA_PERSIST_DIR,
    CODE_EXTENSIONS,
    DEFAULT_EXCLUDE_DIRS,
    DOCUMENT_EXTENSIONS,
    INGEST_LARGE_DIR_THRESHOLD,
    SCIP_INDEXERS,
    STRUCTURED_EXTENSIONS,
)
from .ingestion.ingestion_pipeline import IngestionPipeline
from .ingestion.metadata import MetadataKeys
from .query.engine import QueryEngine
from .storage.chroma_store import ChromaStore
from .storage.document_registry import DocumentRegistry

logger = logging.getLogger(__name__)

# ── Server identity ───────────────────────────────────────────────
_SERVER_NAME    = "abyss"
_SERVER_VERSION = "0.2"

# ── MCP tool names ────────────────────────────────────────────────
_TOOL_INDEX_DIRECTORY        = "index_directory"
_TOOL_LIST_DOCUMENTS         = "list_documents"
_TOOL_REMOVE_DOCUMENT        = "remove_document"
_TOOL_REPLACE_DOCUMENT       = "replace_document"
_TOOL_CLEAR_DATABASE         = "clear_database"
_TOOL_QUERY                  = "query"
_TOOL_LIST_SOURCES           = "list_sources"
_TOOL_LIST_FILTERABLE_FIELDS = "list_filterable_fields"

# ── Resource URIs ─────────────────────────────────────────────────
_RES_STATUS               = "rag://status"
_RES_SUPPORTED_EXTENSIONS = "rag://supported-extensions"
_RES_STATS                = "rag://stats"

# ── Result status values ──────────────────────────────────────────
_STATUS_OK                   = "ok"
_STATUS_ERROR                = "error"
_STATUS_WARNING              = "warning"
_STATUS_REJECTED             = "rejected"
_STATUS_REQUIRES_CONFIRM     = "requires_confirmation"

# ── Filter parameter names ────────────────────────────────────────
_FILT_SOURCES            = "sources"
_FILT_LANGUAGES          = "languages"
_FILT_KINDS              = "kinds"
_FILT_CHUNK_TYPES        = "chunk_types"
_FILT_LINE_MIN           = "line_min"
_FILT_LINE_MAX           = "line_max"
_FILT_MUST_CONTAIN       = "must_contain"
_FILT_FILE_PATH_CONTAINS = "file_path_contains"

# ── ChromaDB fetch ceiling ────────────────────────────────────────
_CHROMA_MAX_FETCH = 10_000

# ── Last indexation state (in-memory, for rag://status) ──────────
_last_indexation: dict[str, Any] = {}


def create_server() -> Server:
    """
    Create and configure the MCP Server with 8 tools and 3 resources.

    Initialize services:
    - ChromaStore (ChromaDB interface)
    - DocumentRegistry (registry of indexed documents)
    - IngestionPipeline (parsing, enrichment, embedding, storage)
    - QueryEngine (semantic search)
    """
    server = Server(_SERVER_NAME)

    # ── Initialisation des services ───────────────────────────────
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", CHROMA_PERSIST_DIR)
    store = ChromaStore(persist_dir=persist_dir)
    registry = DocumentRegistry(store.client)
    pipeline = IngestionPipeline(store=store, registry=registry)
    query_engine = QueryEngine(store=store)


    logger.info(
        "\n"
        "    ___    ____  __  _______ _____\n"
        "   /   |  / __ )\\ \\/ / ___// ___/\n"
        "  / /| | / __  | \\  /\\__ \\ \\__ \\\n"
        " / ___ |/ /_/ / / / ___/ /___/ /\n"
        "/_/  |_/_____/ /_/ /____//____/\n"
    )
    # ── Log available tools ────────────────────────────────────────
    logger.info("Available tools:")
    logger.info("  1. %s - Index a directory recursively", _TOOL_INDEX_DIRECTORY)
    logger.info("  2. %s - List all indexed documents", _TOOL_LIST_DOCUMENTS)
    logger.info("  3. %s - Remove a document from the database", _TOOL_REMOVE_DOCUMENT)
    logger.info("  4. %s - Replace/re-index a document", _TOOL_REPLACE_DOCUMENT)
    logger.info("  5. %s - Clear entire database (irreversible)", _TOOL_CLEAR_DATABASE)
    logger.info("  6. %s - Semantic search with multi-criteria filtering", _TOOL_QUERY)
    logger.info("  7. %s - List indexed sources and filter values", _TOOL_LIST_SOURCES)
    logger.info("  8. %s - Describe filterable metadata fields", _TOOL_LIST_FILTERABLE_FIELDS)

    logger.info("MCP Server '%s' initialized (persist_dir=%s)", server.name, persist_dir)

    # ══════════════════════════════════════════════════════════════
    #  TOOLS — Declaration of 8 tools
    # ══════════════════════════════════════════════════════════════

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            # ── Tool 1 : index_directory ──────────────────────────
            Tool(
                name=_TOOL_INDEX_DIRECTORY,
                description=(
                    "Recursively browse a directory, parse source files "
                    "and documentation, and index them in the vector database. "
                    "If include_extensions is empty, all supported formats are "
                    "indexed (code, docs, PDF, DOCX, images…)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path of the directory to index",
                        },
                        "include_extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Extensions to include (ex: ['.cs', '.py']). "
                                "Empty = all."
                            ),
                            "default": [],
                        },
                        "exclude_extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Extensions to exclude",
                            "default": [],
                        },
                        "confirm_large": {
                            "type": "boolean",
                            "description": (
                                "Set to true to proceed when the file count exceeds "
                                "the large-directory threshold. On first call without "
                                "this flag, the tool returns requires_confirmation "
                                "with the file count so the caller can relay the "
                                "information to the user before re-invoking."
                            ),
                            "default": False,
                        },
                    },
                    "required": ["path"],
                },
            ),

            # ── Tool 2 : list_documents ───────────────────────────
            Tool(
                name=_TOOL_LIST_DOCUMENTS,
                description=(
                    "List all indexed files with their metadata: name, date, size, chunk count."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),

            # ── Tool 3 : remove_document ──────────────────────────
            Tool(
                name=_TOOL_REMOVE_DOCUMENT,
                description=(
                    "Delete a document from the vector database and all its "
                    "chunks. The source file on disk is not touched."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path of the file to remove from index",
                        },
                    },
                    "required": ["file_path"],
                },
            ),

            # ── Tool 4 : replace_document ─────────────────────────
            Tool(
                name=_TOOL_REPLACE_DOCUMENT,
                description=(
                    "Replace a document: delete the old version then "
                    "re-index the file from disk. Useful after "
                    "modifying a file."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path of the file to replace",
                        },
                    },
                    "required": ["file_path"],
                },
            ),

            # ── Tool 5 : clear_database ───────────────────────────
            Tool(
                name=_TOOL_CLEAR_DATABASE,
                description=(
                    "Completely clear the vector database. Delete all "
                    "chunks and the document registry. Irreversible. "
                    "The 'confirm' parameter must be true."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to confirm",
                        },
                    },
                    "required": ["confirm"],
                },
            ),

            # ── Tool 6 : query_codebase ───────────────────────────
            Tool(
                name=_TOOL_QUERY,
                description=(
                    "Semantic search in indexed code and documentation. "
                    "Return the most relevant fragments with scores and "
                    "metadata. Support advanced multi-criteria filtering via "
                    "the 'filters' parameter. Use list_sources to know the "
                    "exact values."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Question in natural language",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (1-20)",
                            "default": 6,
                        },
                        "filters": {
                            "type": "object",
                            "description": (
                                "Optional filters on metadata. "
                                "All combined with AND logic."
                            ),
                            "properties": {
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Exact file paths (via list_sources)",
                                },
                                "languages": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Languages (ex: ['csharp', 'python'])",
                                },
                                "kinds": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Symbol types (ex: ['method', 'class'])",
                                },
                                "chunk_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Chunk types (ex: ['code', 'document'])",
                                },
                                "file_path_contains": {
                                    "type": "string",
                                    "description": "Substring in the file path",
                                },
                                "line_min": {
                                    "type": "integer",
                                    "description": "Minimum start line",
                                },
                                "line_max": {
                                    "type": "integer",
                                    "description": "Maximum end line",
                                },
                                "must_contain": {
                                    "type": "string",
                                    "description": "Required word/phrase in the chunk text",
                                },
                            },
                        },
                        "language_filter": {
                            "type": "string",
                            "description": "[BACK-COMPAT] Prefer filters.languages",
                            "default": "",
                        },
                        "kind_filter": {
                            "type": "string",
                            "description": "[BACK-COMPAT] Prefer filters.kinds",
                            "default": "",
                        },
                        "file_path_filter": {
                            "type": "string",
                            "description": "[BACK-COMPAT] Prefer filters.file_path_contains",
                            "default": "",
                        },
                    },
                    "required": ["question"],
                },
            ),

            # ── Tool 7 : list_sources ─────────────────────────────
            Tool(
                name=_TOOL_LIST_SOURCES,
                description=(
                    "List unique values present in the database: file paths, "
                    "programming languages, symbol kinds, chunk types. "
                    "Use before querying to know available filter values."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),

            # ── Tool 8 : list_filterable_fields ───────────────────
            Tool(
                name=_TOOL_LIST_FILTERABLE_FIELDS,
                description=(
                    "Describe metadata fields available for filtering in "
                    "query_codebase, with types, supported operators and "
                    "example values."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    # ══════════════════════════════════════════════════════════════
    #  TOOLS — Dispatch and execution
    # ══════════════════════════════════════════════════════════════

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        global _last_indexation

        logger.info("Tool called: %s(%s)", name, json.dumps(arguments, default=str)[:200])

        try:
            result: dict

            # ── index_directory ───────────────────────────────────
            if name == _TOOL_INDEX_DIRECTORY:
                path = arguments["path"]
                include = set(arguments.get("include_extensions") or [])
                exclude = set(arguments.get("exclude_extensions") or [])

                if not include:
                    include = ALL_SUPPORTED_EXTENSIONS.copy()
                effective = include - exclude

                result = await pipeline.ingest_directory(
                    directory=path,
                    extensions=effective,
                    exclude_dirs=DEFAULT_EXCLUDE_DIRS,
                )

                # Remember the last indexation
                _last_indexation = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "path": path,
                    "files_processed": result.get("files_processed", 0),
                    "chunks_created": result.get("chunks_created", 0),
                    "ingestion_stats": result.get("ingestion_stats", {}),
                }

            # ── list_documents ────────────────────────────────────
            elif name == _TOOL_LIST_DOCUMENTS:
                docs = registry.list_all()
                total_chunks = sum(
                    d.get("chunk_count", 0) for d in docs
                    if isinstance(d.get("chunk_count"), (int, float))
                )
                result = {
                    "status": _STATUS_OK,
                    "total_documents": len(docs),
                    "total_chunks": total_chunks,
                    "documents": docs,
                }

            # ── remove_document ───────────────────────────────────
            elif name == _TOOL_REMOVE_DOCUMENT:
                file_path = arguments["file_path"]
                if not registry.exists(file_path):
                    result = {
                        "status": _STATUS_WARNING,
                        "removed": False,
                        "file_path": file_path,
                        "chunks_deleted": 0,
                        "message": "Document not found in index",
                    }
                else:
                    chunks_deleted = store.delete_by_file(file_path)
                    registry.unregister(file_path)
                    result = {
                        "status": _STATUS_OK,
                        "removed": True,
                        "file_path": file_path,
                        "chunks_deleted": chunks_deleted,
                    }

            # ── replace_document ──────────────────────────────────
            elif name == _TOOL_REPLACE_DOCUMENT:
                file_path = arguments["file_path"]
                if not Path(file_path).is_file():
                    result = {
                        "status": _STATUS_ERROR,
                        "replaced": False,
                        "file_path": file_path,
                        "message": "Unable to access file on disk",
                    }
                else:
                    old_chunks = store.delete_by_file(file_path)
                    registry.unregister(file_path)
                    ingest_result = await pipeline.ingest_single_file(file_path)
                    result = {
                        "status": _STATUS_OK,
                        "replaced": True,
                        "file_path": file_path,
                        "old_chunks_deleted": old_chunks,
                        "new_chunks_created": ingest_result.get("chunks_created", 0),
                        "scip_enriched": ingest_result.get("scip_enriched", 0),
                    }

            # ── clear_database ────────────────────────────────────
            elif name == _TOOL_CLEAR_DATABASE:
                if not arguments.get("confirm", False):
                    result = {
                        "status": _STATUS_REJECTED,
                        "message": "confirm must be true",
                        "cleared": False,
                    }
                else:
                    doc_count = len(registry.list_all())
                    chunk_count = store.count()
                    store.clear_all()
                    registry.clear()
                    _last_indexation = {}
                    result = {
                        "status": _STATUS_OK,
                        "cleared": True,
                        "documents_removed": doc_count,
                        "chunks_removed": chunk_count,
                    }

            # ── query_codebase (v2 enrichi) ───────────────────────
            elif name == _TOOL_QUERY:
                question = arguments["question"]
                top_k = min(arguments.get("top_k", 6), 20)

                # Merge v1 filters (backwards compat) and v2 filters (enriched)
                filters = dict(arguments.get("filters") or {})
                if lang := arguments.get("language_filter"):
                    filters.setdefault(_FILT_LANGUAGES, []).append(lang)
                if kind := arguments.get("kind_filter"):
                    filters.setdefault(_FILT_KINDS, []).append(kind)
                if fp := arguments.get("file_path_filter"):
                    filters.setdefault(_FILT_FILE_PATH_CONTAINS, fp)

                # Validate sources
                if filters.get(_FILT_SOURCES):
                    known = _get_known_sources(store)
                    unknown = [s for s in filters[_FILT_SOURCES] if s not in known]
                    if unknown:
                        result = {
                            "status": _STATUS_ERROR,
                            "message": f"Unknown sources: {', '.join(unknown)}",
                            "available_sources": sorted(known)[:20],
                            "hint": "Use list_sources for exact paths.",
                        }
                    else:
                        where = _build_where_clause(filters)
                        where_doc = (
                            {"$contains": filters[_FILT_MUST_CONTAIN]}
                            if filters.get(_FILT_MUST_CONTAIN) else None
                        )
                        result = await query_engine.query(
                            question=question,
                            top_k=top_k,
                            where=where,
                            where_document=where_doc,
                        )
                        if filters:
                            result["filters_applied"] = filters
                else:
                    where = _build_where_clause(filters)
                    where_doc = (
                        {"$contains": filters[_FILT_MUST_CONTAIN]}
                        if filters.get(_FILT_MUST_CONTAIN) else None
                    )
                    result = await query_engine.query(
                        question=question,
                        top_k=top_k,
                        where=where,
                        where_document=where_doc,
                    )
                    if filters:
                        result["filters_applied"] = filters

            # ── list_sources (enrichi) ────────────────────────────
            elif name == _TOOL_LIST_SOURCES:
                all_data = store.collection.get(
                    include=["metadatas"], limit=_CHROMA_MAX_FETCH,
                )
                metadatas = all_data.get("metadatas") or []
                sources: set[str] = set()
                languages: set[str] = set()
                kinds: set[str] = set()
                chunk_types: set[str] = set()
                for meta in metadatas:
                    if not meta:
                        continue
                    if v := meta.get(MetadataKeys.FILE_PATH):
                        sources.add(v)
                    if v := meta.get(MetadataKeys.LANGUAGE):
                        languages.add(v)
                    if v := meta.get(MetadataKeys.KIND):
                        kinds.add(v)
                    if v := meta.get(MetadataKeys.CHUNK_TYPE):
                        chunk_types.add(v)
                result = {
                    "status": _STATUS_OK,
                    "sources": sorted(sources),
                    "available_languages": sorted(languages),
                    "available_kinds": sorted(kinds),
                    "available_chunk_types": sorted(chunk_types),
                }

            # ── list_filterable_fields (enrichi) ──────────────────
            elif name == _TOOL_LIST_FILTERABLE_FIELDS:
                result = {
                    "status": _STATUS_OK,
                    "fields": [
                        {"name": MetadataKeys.LANGUAGE, "type": "string",
                         "description": "Programming language",
                         "operators": ["exact match", "in list"]},
                        {"name": MetadataKeys.KIND, "type": "string",
                         "description": "SCIP symbol type",
                         "operators": ["exact match", "in list"]},
                        {"name": MetadataKeys.CHUNK_TYPE, "type": "string",
                         "description": "Content type",
                         "operators": ["exact match", "in list"]},
                        {"name": MetadataKeys.FILE_PATH, "type": "string",
                         "description": "Source file path",
                         "operators": ["exact match", "in list", "substring"]},
                        {"name": MetadataKeys.START_LINE, "type": "integer",
                         "description": "Chunk start line",
                         "operators": [">=", "<="]},
                        {"name": MetadataKeys.END_LINE, "type": "integer",
                         "description": "Chunk end line",
                         "operators": [">=", "<="]},
                        {"name": MetadataKeys.DISPLAY_NAME, "type": "string",
                         "description": "Human-readable symbol name",
                         "operators": ["exact match"]},
                    ],
                }

            # ── Unknown tool ──────────────────────────────────────
            else:
                result = {"error": f"Unknown tool: {name}"}

        except Exception as e:
            logger.exception("Error in tool %s", name)
            result = {"status": _STATUS_ERROR, "message": str(e)}

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str, ensure_ascii=False),
        )]

    # ══════════════════════════════════════════════════════════════
    #  RESOURCES — Declaration and reading
    # ══════════════════════════════════════════════════════════════

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri=_RES_STATUS,
                name="Server Status",
                description="Server status, number of documents and indexed chunks",
                mimeType="application/json",
            ),
            Resource(
                uri=_RES_SUPPORTED_EXTENSIONS,
                name="Supported Extensions",
                description="List of supported file extensions with associated parser",
                mimeType="application/json",
            ),
            Resource(
                uri=_RES_STATS,
                name="Detailed Statistics",
                description="Detailed statistics: breakdown by language, kind, type",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:

        # ── rag://status ──────────────────────────────────────────
        if uri == _RES_STATUS:
            docs = registry.list_all()
            data = {
                "server": _SERVER_NAME,
                "version": _SERVER_VERSION,
                "status": "running",
                "database": {
                    "persist_dir": persist_dir,
                    "total_documents": len(docs),
                    "total_chunks": store.count(),
                },
                "last_indexation": _last_indexation or None,
            }
            return json.dumps(data, indent=2, default=str)

        # ── rag://supported-extensions ────────────────────────────
        elif uri == _RES_SUPPORTED_EXTENSIONS:
            data = {
                "code_extensions": {
                    ext: {
                        "parser": "tree-sitter",
                        "language": lang,
                        "scip": SCIP_INDEXERS.get(lang),
                    }
                    for ext, lang in CODE_EXTENSIONS.items()
                },
                "structured_extensions": {
                    ext: {"parser": "json.loads" if ext == ".json" else "ElementTree"}
                    for ext in sorted(STRUCTURED_EXTENSIONS)
                },
                "document_extensions": {
                    ext: {"reader": "SimpleDirectoryReader (auto)"}
                    for ext in sorted(DOCUMENT_EXTENSIONS)
                },
                "total_extensions": len(ALL_SUPPORTED_EXTENSIONS),
            }
            return json.dumps(data, indent=2)

        # ── rag://stats ───────────────────────────────────────────
        elif uri == _RES_STATS:
            data = _compute_stats(store, registry)
            return json.dumps(data, indent=2, default=str)

        else:
            return json.dumps({"error": f"Unknown resource: {uri}"})

    return server


# ══════════════════════════════════════════════════════════════════
#  Utility functions (outside closure)
# ══════════════════════════════════════════════════════════════════


def _get_known_sources(store: ChromaStore) -> set[str]:
    """Retourne l'ensemble des file_path uniques dans ChromaDB."""
    all_data = store.collection.get(include=["metadatas"], limit=_CHROMA_MAX_FETCH)
    sources: set[str] = set()
    for m in (all_data.get("metadatas") or []):
        if m and (fp := m.get(MetadataKeys.FILE_PATH)) and isinstance(fp, str):
            sources.add(fp)
    return sources


def _build_where_clause(filters: dict) -> dict | None:
    """
    Translate semantic filters to ChromaDB syntax.
    100% deterministic translation — LLM never sees $and/$gte/$in.
    """
    conditions: list[dict] = []

    if sources := filters.get(_FILT_SOURCES):
        if len(sources) == 1:
            conditions.append({MetadataKeys.FILE_PATH: sources[0]})
        else:
            conditions.append({MetadataKeys.FILE_PATH: {"$in": sources}})

    if languages := filters.get(_FILT_LANGUAGES):
        if len(languages) == 1:
            conditions.append({MetadataKeys.LANGUAGE: languages[0]})
        else:
            conditions.append({MetadataKeys.LANGUAGE: {"$in": languages}})

    if kinds := filters.get(_FILT_KINDS):
        if len(kinds) == 1:
            conditions.append({MetadataKeys.KIND: kinds[0]})
        else:
            conditions.append({MetadataKeys.KIND: {"$in": kinds}})

    if chunk_types := filters.get(_FILT_CHUNK_TYPES):
        if len(chunk_types) == 1:
            conditions.append({MetadataKeys.CHUNK_TYPE: chunk_types[0]})
        else:
            conditions.append({MetadataKeys.CHUNK_TYPE: {"$in": chunk_types}})

    if line_min := filters.get(_FILT_LINE_MIN):
        conditions.append({MetadataKeys.START_LINE: {"$gte": line_min}})
    if line_max := filters.get(_FILT_LINE_MAX):
        conditions.append({MetadataKeys.END_LINE: {"$lte": line_max}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _compute_stats(store: ChromaStore, registry: DocumentRegistry) -> dict:
    """
    Compute detailed statistics by browsing metadata
    des chunks dans ChromaDB.
    """
    total = store.count()
    if total == 0:
        return {
            "total_chunks": 0,
            "by_chunk_type": {},
            "by_language": {},
            "by_kind": {},
            "by_doc_type": {},
        }

    all_data = store.collection.get(
        include=["metadatas"],
        limit=min(total, _CHROMA_MAX_FETCH),
    )
    metadatas = all_data.get("metadatas") or []

    by_chunk_type: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    by_doc_type: dict[str, int] = {}

    for meta in metadatas:
        if not meta:
            continue

        ct = meta.get(MetadataKeys.CHUNK_TYPE, "unknown")
        by_chunk_type[ct] = by_chunk_type.get(ct, 0) + 1

        if lang := meta.get(MetadataKeys.LANGUAGE):
            by_language[lang] = by_language.get(lang, 0) + 1

        if kind := meta.get(MetadataKeys.KIND):
            by_kind[kind] = by_kind.get(kind, 0) + 1

        if dt := meta.get(MetadataKeys.DOC_TYPE):
            by_doc_type[dt] = by_doc_type.get(dt, 0) + 1

    return {
        "total_chunks": total,
        "by_chunk_type": dict(sorted(by_chunk_type.items(), key=lambda x: -x[1])),
        "by_language": dict(sorted(by_language.items(), key=lambda x: -x[1])),
        "by_kind": dict(sorted(by_kind.items(), key=lambda x: -x[1])),
        "by_doc_type": dict(sorted(by_doc_type.items(), key=lambda x: -x[1])),
    }


def _count_matching_files(
    directory: str,
    extensions: set[str],
    exclude_dirs: list[str],
) -> int:
    """
    Fast directory walk that counts files matching the given extensions.

    No parsing, no embedding — pure filesystem traversal.
    Used by the large-directory pre-check gate (RQ-BIN-002, DEC-BIN-002).

    Args:
        directory:    Root directory to scan.
        extensions:   Set of extensions to count (e.g. {".cs", ".py"}).
        exclude_dirs: Directory names to skip during traversal.

    Returns:
        Count of matching files.
    """
    root = Path(directory)
    if not root.is_dir():
        return 0

    exclude_set = set(exclude_dirs)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        for filename in filenames:
            if Path(filename).suffix.lower() in extensions:
                count += 1
    return count
