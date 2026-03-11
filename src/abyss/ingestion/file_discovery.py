# ingestion/file_discovery.py — File discovery and classification
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from ..config import (
    ALL_SUPPORTED_EXTENSIONS,
    CODE_EXTENSIONS,
    DEFAULT_EXCLUDE_DIRS,
    DOCUMENT_EXTENSIONS,
    STRUCTURED_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# Maximum size of a file to index (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileType(Enum):
    """Enumeration of file type classifications."""
    CODE = "code"
    STRUCTURED = "structured"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class FileDiscovery:
    """
    Discover and classify files in a directory tree.

    Responsibilities:
    - Recursively enumerate files matching the configured extensions.
    - Skip files that are too large, empty, or in excluded directories.
    - Classify each file as 'code', 'structured', 'document', or 'unknown'.
    - Resolve the tree-sitter language identifier for code files.
    """

    def __init__(
        self,
        extensions: set[str] | None = None,
        exclude_dirs: list[str] | None = None,
        exclude_extensions: set[str] | None = None,
    ) -> None:
        """
        Args:
            extensions:         Extensions to include (default: all supported).
            exclude_dirs:       Directory names to skip (default: DEFAULT_EXCLUDE_DIRS).
            exclude_extensions: Extensions to exclude explicitly.
        """
        self._extensions: set[str] = extensions if extensions is not None else ALL_SUPPORTED_EXTENSIONS
        self._exclude_dirs: list[str] = exclude_dirs if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS
        self._exclude_extensions: set[str] = exclude_extensions or set()

    def discover(self, directory: str | Path) -> list[Path]:
        """
        Recursively enumerate files in *directory* matching the configuration.

        Args:
            directory: Root path to scan.

        Returns:
            Sorted list of matching Path objects.

        Raises:
            FileNotFoundError: If *directory* does not exist.
        """
        directory = Path(directory).resolve()

        if not directory.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        exclude_set = set(self._exclude_dirs)
        effective_extensions = self._extensions - self._exclude_extensions

        files: list[Path] = []

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip excluded directories
            parts = file_path.relative_to(directory).parts
            if any(part in exclude_set for part in parts[:-1]):
                continue

            # Filter by extension
            if file_path.suffix.lower() not in effective_extensions:
                continue

            # Filter by size
            try:
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    logger.warning("File too large (%d bytes), ignored: %s", size, file_path)
                    continue
                if size == 0:
                    logger.debug("Empty file, ignored: %s", file_path)
                    continue
            except OSError as e:
                logger.warning("Unable to access %s: %s", file_path, e)
                continue

            files.append(file_path)

        files.sort(key=lambda p: str(p).lower())
        logger.info(
            "Discovery: %d files in %s (extensions=%d, excluded=%d dirs)",
            len(files), directory, len(effective_extensions), len(exclude_set),
        )
        return files

    def classify(self, file_path: Path) -> FileType:
        """
        Classify a file by its extension.

        Returns:
            FileType enum (CODE | STRUCTURED | DOCUMENT | UNKNOWN)
        """
        ext = file_path.suffix.lower()
        if ext in CODE_EXTENSIONS:
            return FileType.CODE
        elif ext in STRUCTURED_EXTENSIONS:
            return FileType.STRUCTURED
        elif ext in DOCUMENT_EXTENSIONS:
            return FileType.DOCUMENT
        return FileType.UNKNOWN

    def get_language(self, file_path: Path) -> str | None:
        """
        Return the tree-sitter language identifier for a code file.
        Returns None if the extension is not a recognised code type.
        """
        return CODE_EXTENSIONS.get(file_path.suffix.lower())
