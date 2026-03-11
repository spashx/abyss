# config.py — Configuration and constants of the RAG MCP server
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

# ══════════════════════════════════════════════════════════════════════════
#  Logger Setup
# ══════════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  Built-in Default Values (used as fallback if config.yaml is missing)
# ══════════════════════════════════════════════════════════════════════════

# Source code extensions → tree-sitter language
_DEFAULT_CODE_EXTENSIONS: dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".java": "java",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".html": "html",
    ".htm": "html",
}

# Structured file extensions (JSON, XML…)
_DEFAULT_STRUCTURED_EXTENSIONS: set[str] = {
    ".json",
    ".xml",
    ".csproj",
    ".props",
    ".config",
}

# Document extensions (text, archives, office, etc.)
_DEFAULT_DOCUMENT_EXTENSIONS: set[str] = {
    ".md",
    ".txt",
    ".rst",
    ".pdf",
    ".docx",
    ".pptx",
    ".epub",
    ".ipynb",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".xlsx",
}

# Extensions to exclude from indexing (binary and compiled artifacts)
_DEFAULT_EXCLUDE_EXTENSIONS: set[str] = {
    ".bin",
    ".exe",
    ".dll",
    ".obj",
    ".pdb",
}

# Directories to exclude
_DEFAULT_EXCLUDE_DIRS: list[str] = [
    "node_modules",
    ".git",
    ".svn",
    ".hg",
    "bin",
    "obj",
    "dist",
    "build",
    ".vs",
    ".idea",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "venv",
    ".venv",
    ".github",
    ".vscode",
    "Debug",
    "Release",
]

# SCIP — Indexers by language
_DEFAULT_SCIP_INDEXERS: dict[str, str] = {
    "dotnet": "scip-dotnet",
    "python": "scip-python",
    "java": "scip-java",
    "typescript": "scip-typescript",
    "javascript": "scip-typescript",
}

# ChromaDB persist directory
_DEFAULT_CHROMA_PERSIST_DIR: str = "data/chroma_db"

# Embedding model
_DEFAULT_EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_EMBEDDING_CACHE_DIR: str = str(Path(__file__).parent.parent.parent / "data" / "models")
_DEFAULT_CHUNK_OVERLAP_RATIO: float = 0.2

# EmbedBuilder configuration
_DEFAULT_EMBED_BUILDER_DEBUG: bool = False
_DEFAULT_EMBED_BUILDER_OUTPUT_DIR: str = "logs/EmbedBuilder"

# Logging levels for stdout/stderr (per-logger granularity)
# You can override these in config.yaml to control verbosity of specific loggers.
# Valid values: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
_DEFAULT_ABYSS_LOG_LEVEL: str = "INFO"  # Root logger (abyss + stdlib)
_DEFAULT_CHROMADB_LOG_LEVEL: str = "INFO"  # Reduces ChromaDB verbosity
_DEFAULT_HTTPX_LOG_LEVEL: str = "INFO"  # Reduces HTTP client verbosity
_DEFAULT_LLAMA_INDEX_LOG_LEVEL: str = "INFO"  # Reduces LlamaIndex node parser verbosity

# ══════════════════════════════════════════════════════════════════════════
#  Configuration Loading
# ══════════════════════════════════════════════════════════════════════════


def _load_config_from_yaml() -> dict[str, Any]:
    """
    Load configuration from config.yaml at the project root.
    Returns an empty dict if the file does not exist.
    """
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    
    if not config_path.exists():
        logger.warning(
            f"Configuration file not found at {config_path}. "
            "Using built-in defaults."
        )
        return {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.info(f"Configuration loaded successfully from {config_path}")
        return config
    except Exception as e:
        logger.error(
            f"Failed to load configuration from {config_path}: {e}. "
            "Using built-in defaults."
        )
        return {}


def _get_config_value(
    config: dict[str, Any],
    key: str,
    default: Any,
    type_hint: type = None,
) -> Any:
    """
    Extract a configuration value with fallback to default.
    Logs appropriately based on whether the value was found or a default was used.
    
    Args:
        config: The loaded configuration dictionary
        key: The configuration key to retrieve
        default: The built-in default value
        type_hint: Optional type to validate against (for type checking purposes)
    
    Returns:
        The configuration value or the default
    """
    if key in config:
        return config[key]
    return default


# Load configuration once at module initialization
_config = _load_config_from_yaml()

# ══════════════════════════════════════════════════════════════════════════
#  Public Configuration Variables
# ══════════════════════════════════════════════════════════════════════════

# Source code extensions → tree-sitter language
CODE_EXTENSIONS: dict[str, str] = _get_config_value(
    _config, "code_extensions", _DEFAULT_CODE_EXTENSIONS
)

# Structured file extensions (JSON, XML…)
_structured_list = _get_config_value(
    _config, "structured_extensions", list(_DEFAULT_STRUCTURED_EXTENSIONS)
)
STRUCTURED_EXTENSIONS: set[str] = set(_structured_list)

# Document extensions (SimpleDirectoryReader)
_document_list = _get_config_value(
    _config, "document_extensions", list(_DEFAULT_DOCUMENT_EXTENSIONS)
)
DOCUMENT_EXTENSIONS: set[str] = set(_document_list)

# Union of all supported extensions
ALL_SUPPORTED_EXTENSIONS: set[str] = (
    set(CODE_EXTENSIONS.keys()) | STRUCTURED_EXTENSIONS | DOCUMENT_EXTENSIONS
)

# Directories to exclude
DEFAULT_EXCLUDE_DIRS: list[str] = _get_config_value(
    _config, "exclude_dirs", _DEFAULT_EXCLUDE_DIRS
)

# Extensions to exclude from indexing
_exclude_ext_list = _get_config_value(
    _config, "exclude_extensions", list(_DEFAULT_EXCLUDE_EXTENSIONS)
)
EXCLUDE_EXTENSIONS: set[str] = set(_exclude_ext_list)

# SCIP — Indexers by language
SCIP_INDEXERS: dict[str, str] = _get_config_value(
    _config, "scip_indexers", _DEFAULT_SCIP_INDEXERS
)

# ChromaDB persist directory
CHROMA_PERSIST_DIR: str = _get_config_value(
    _config, "chroma_persist_dir", _DEFAULT_CHROMA_PERSIST_DIR
)

# Embedding model
EMBEDDING_MODEL_NAME: str = _get_config_value(
    _config, "embedding_model_name", _DEFAULT_EMBEDDING_MODEL_NAME
)

# Local cache directory for the embedding model snapshot
EMBEDDING_CACHE_DIR: str = _get_config_value(
    _config, "embedding_cache_dir", _DEFAULT_EMBEDDING_CACHE_DIR
)

# Chunk overlap ratio
CHUNK_OVERLAP_RATIO: float = _get_config_value(
    _config, "chunk_overlap_ratio", _DEFAULT_CHUNK_OVERLAP_RATIO
)

# EmbedBuilder configuration
EMBED_BUILDER_DEBUG: bool = _get_config_value(
    _config, "embed_builder_debug", _DEFAULT_EMBED_BUILDER_DEBUG
)

EMBED_BUILDER_DEBUG_OUTPUT_DIR: str = _get_config_value(
    _config, "embed_builder_debug_output_dir", _DEFAULT_EMBED_BUILDER_OUTPUT_DIR
)

# ══════════════════════════════════════════════════════════════════════════
#  Logging Configuration
# ══════════════════════════════════════════════════════════════════════════
# These values control verbosity for different loggers.
# Override in config.yaml using logging level names: "DEBUG", "INFO", "WARNING", etc.

# Root logger level (controls all logs to stderr/filehandler)
ABYSS_LOG_LEVEL: str = _get_config_value(
    _config, "abyss_log_level", _DEFAULT_ABYSS_LOG_LEVEL
)

# Chromadb module logger level (default=INFO to reduce noise)
CHROMADB_LOG_LEVEL: str = _get_config_value(
    _config, "chromadb_log_level", _DEFAULT_CHROMADB_LOG_LEVEL
)

# HTTPX module logger level (default=INFO to reduce noise)
HTTPX_LOG_LEVEL: str = _get_config_value(
    _config, "httpx_log_level", _DEFAULT_HTTPX_LOG_LEVEL
)

# LlamaIndex node parser logger level (default=INFO to reduce noise from chunking)
LLAMA_INDEX_LOG_LEVEL: str = _get_config_value(
    _config, "llama_index_log_level", _DEFAULT_LLAMA_INDEX_LOG_LEVEL
)

_CONFIG_KEYS = [
    "code_extensions", "structured_extensions", "document_extensions",
    "exclude_dirs", "exclude_extensions", "scip_indexers",
    "chroma_persist_dir",
    "embedding_model_name", "embedding_cache_dir", "chunk_overlap_ratio",
    "embed_builder_debug", "embed_builder_debug_output_dir",
]
_n_from_file = sum(1 for k in _CONFIG_KEYS if k in _config)
logger.info(
    "Abyss configuration: %d/%d keys from config.yaml, %d using built-in defaults",
    _n_from_file, len(_CONFIG_KEYS), len(_CONFIG_KEYS) - _n_from_file,
)
