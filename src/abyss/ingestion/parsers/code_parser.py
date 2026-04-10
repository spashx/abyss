# ingestion/parsers/code_parser.py — Source code parsing via tree-sitter
from __future__ import annotations

import logging
from pathlib import Path

from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from llama_index.core.schema import TextNode

from ...config import CODE_EXTENSIONS
from ..metadata import MetadataKeys
from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# Default parameters of CodeSplitter
DEFAULT_CHUNK_LINES = 60
DEFAULT_CHUNK_LINES_OVERLAP = 10
DEFAULT_MAX_CHARS = 1000


class CodeParser(BaseParser):
    """
    Parse source code files via tree-sitter CodeSplitter.

    Splits code into chunks aligned on syntactic boundaries
    (functions, classes, methods). Falls back to SentenceSplitter
    if tree-sitter does not support the language.

    The splitter instances are cached per language to avoid
    repeated initialisation cost.
    """

    def __init__(
        self,
        chunk_lines: int = DEFAULT_CHUNK_LINES,
        chunk_overlap: int = DEFAULT_CHUNK_LINES_OVERLAP,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._chunk_lines = chunk_lines
        self._chunk_overlap = chunk_overlap
        self._max_chars = max_chars
        # Cache of CodeSplitter instances keyed by language
        self._splitter_cache: dict[str, CodeSplitter] = {}

    # ── Public interface ────────────────────────────────────────

    def parse(self, file_path: Path) -> list[TextNode]:
        """
        Parse a source code file and return a list of TextNode chunks.

        Args:
            file_path: Absolute path of the source file.

        Returns:
            List of TextNode with code metadata (file_path, file_name,
            language, chunk_type, start_line, end_line).
        """
        ext = file_path.suffix.lower()
        language = CODE_EXTENSIONS.get(ext)

        if not language:
            logger.warning("Unrecognised code extension: %s", ext)
            return []

        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Unable to read %s: %s", file_path, e)
            return []

        if not raw.strip():
            return []

        # Attempt tree-sitter parsing
        try:
            splitter = self._get_or_create_splitter(language)
            from llama_index.core import Document
            doc = Document(text=raw, metadata={"file_path": str(file_path)})
            nodes = splitter.get_nodes_from_documents([doc])
        except Exception as e:
            logger.warning(
                "tree-sitter failed for %s (%s): %s — fallback",
                file_path.name, language, e,
            )
            nodes = self._fallback_split(raw)

        # Enrich metadata for each node
        result: list[TextNode] = []
        for node in nodes:
            start_line, end_line = self._add_line_numbers(raw, node.text)
            result.append(TextNode(
                text=node.text,
                metadata={
                    MetadataKeys.FILE_PATH:  str(file_path),
                    MetadataKeys.FILE_NAME:  file_path.name,
                    MetadataKeys.LANGUAGE:   language,
                    MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_CODE,
                    MetadataKeys.START_LINE: start_line,
                    MetadataKeys.END_LINE:   end_line,
                },
            ))
        logger.info(
            "Code parsed: %s => %d chunks (lang=%s)",
            file_path.name, len(result), language,
        )
        return result

    # ── Private helpers ─────────────────────────────────────────

    def _get_or_create_splitter(self, language: str) -> CodeSplitter:
        """Return a CodeSplitter cached by language."""
        key = f"{language}:{self._chunk_lines}:{self._chunk_overlap}:{self._max_chars}"
        if key not in self._splitter_cache:
            self._splitter_cache[key] = CodeSplitter(
                language=language,
                chunk_lines=self._chunk_lines,
                chunk_lines_overlap=self._chunk_overlap,
                max_chars=self._max_chars,
            )
        return self._splitter_cache[key]

    def _fallback_split(self, raw: str) -> list[TextNode]:
        """
        Fallback when tree-sitter fails.
        Uses LlamaIndex SentenceSplitter to split by sentences.
        """
        from llama_index.core import Document
        doc = Document(text=raw)
        splitter = SentenceSplitter(
            chunk_size=self._max_chars,
            chunk_overlap=200,
        )
        return splitter.get_nodes_from_documents([doc])

    @staticmethod
    def _add_line_numbers(full_text: str, chunk_text: str) -> tuple[int, int]:
        """
        Find the 1-based start and end line numbers of a chunk
        within the full file text.

        Returns:
            (start_line, end_line)
        """
        idx = full_text.find(chunk_text)
        if idx == -1:
            return (1, 1)
        start_line = full_text[:idx].count("\n") + 1
        end_line = start_line + chunk_text.count("\n")
        return (start_line, end_line)
