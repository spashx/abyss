# ingestion/parsers/doc_parser.py — Document parsing via SimpleDirectoryReader
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

try:
    from markitdown import MarkItDown
except ImportError as _err:  # REQ-07
    raise ImportError(
        "markitdown is required. Install it with: pip install markitdown[all]"
    ) from _err

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode

from .base_parser import BaseParser
from ..metadata import MetadataKeys

logger = logging.getLogger(__name__)

# Extensions processed by the custom Markdown pipeline
MARKDOWN_EXTENSIONS = {".md"}


# ── Internal section-dict keys (private to this module) ─────────────────────
# These keys are used exclusively by the _split_by_headers / _aggregate_nodes /
# _make_node / _split_large_section pipeline. Defining them as constants avoids
# silent typo-induced KeyError bugs and makes refactoring trivial.
_K_LEVEL         = "level"
_K_TITLE         = "title"
_K_CONTENT       = "content"
_K_CONTENT_LINES = "content_lines"
_K_START_LINE    = "start_line"
_K_END_LINE      = "end_line"

class DocumentParser(BaseParser):
    """
    Parse document files (Markdown, PDF, DOCX, TXT…) into TextNode chunks.

    Strategy
    --------
    - Markdown (.md)
        Custom header-based pipeline:
          1. _split_by_headers()    – regex split on # … ###### levels
          2. _aggregate_nodes()     – merge small sections up to chunk_size
          3. _split_large_section() – paragraph-level split with overlap
        Metadata per chunk: section_hierarchy, header_levels, start_line,
        end_line, has_code_blocks, code_block_count, word_count.

    - Other formats (PDF, DOCX, PPTX, TXT…)
        1. _convert_with_markitdown() – in-memory conversion to Markdown
           (Microsoft MarkItDown library, all plugins enabled)
        2. On success → same _parse_markdown() pipeline as native .md files.
           Metadata extras: markitdown_converted=True, original_doc_type=<ext>,
           file_name=<name>.abyss.md.
        3. On failure / empty output → SentenceSplitter fallback (PDF, DOCX…)

    SimpleDirectoryReader is used for the fallback path and for initial loading
    of Markdown files (PDFReader, DocxReader… depending on file type).

    Also exposes parse_fallback() for files whose type is 'unknown'.
    """

    def __init__(self, chunk_size: int = 1_000, chunk_overlap: int = 200) -> None:
        """
        Initialise the parser and a shared MarkItDown instance (REQ-02).

        Args:
            chunk_size:    Target chunk size in characters.
            chunk_overlap: Overlap in characters for text-based splitting.
        """
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        # Single shared instance — all plugins enabled (REQ-02)
        self._markitdown = MarkItDown(enable_plugins=True)

    def parse(self, file_path: Path) -> list[TextNode]:
        """
        Parse a document file and return a list of TextNode chunks.

        Args:
            file_path: Absolute path of the file.

        Returns:
            List of TextNode with document metadata
            (file_path, file_name, chunk_type, doc_type,
            section_hierarchy / section_title / section_level for Markdown).
        """
        try:
            reader = SimpleDirectoryReader(input_files=[str(file_path)])
            documents = reader.load_data()
        except Exception as e:
            logger.error("Unable to load %s: %s", file_path, e)
            return []

        if not documents:
            return []

        ext = file_path.suffix.lower()
        base_meta = {
            MetadataKeys.FILE_PATH:  str(file_path),
            MetadataKeys.FILE_NAME:  file_path.name,
            MetadataKeys.CHUNK_TYPE: MetadataKeys.CHUNK_TYPE_DOCUMENT,
            MetadataKeys.DOC_TYPE:   ext.lstrip("."),
        }

        if ext in MARKDOWN_EXTENSIONS:
            # Re-assemble the full text (SimpleDirectoryReader may split pages)
            full_text = "\n".join(doc.text for doc in documents)
            nodes = self._parse_markdown(full_text, base_meta)
        else:
            # REQ-01/03: attempt in-memory markitdown conversion first
            md_text = self._convert_with_markitdown(file_path)
            if md_text:
                # REQ-04: enrich metadata to identify converted documents
                base_meta[MetadataKeys.MARKITDOWN_CONVERTED] = True
                base_meta[MetadataKeys.ORIGINAL_DOC_TYPE] = ext.lstrip(".")
                logger.info(
                    "markitdown: successfully converted %s to Markdown",
                    file_path.name,
                )
                nodes = self._parse_markdown(md_text, base_meta)
            else:
                # REQ-05: fallback to SentenceSplitter when conversion fails
                for doc in documents:
                    doc.metadata.update(base_meta)
                splitter = SentenceSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
                nodes = splitter.get_nodes_from_documents(documents)

        logger.info(
            "Document parsed: %s => %d chunks (type=%s)",
            file_path.name, len(nodes), ext,
        )
        return nodes

    def parse_fallback(self, file_path: Path) -> list[TextNode]:
        """
        Fallback for files classified as 'unknown'.
        Reads the file as plain UTF-8 text and splits by sentences.

        Args:
            file_path: Absolute path of the file.

        Returns:
            List of TextNode with chunk_type='document' and parser_fallback=True.
        """
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Fallback: Unable to read %s: %s", file_path, e)
            return []

        if not text.strip():
            return []

        from llama_index.core import Document

        doc = Document(
            text=text,
            metadata={
                MetadataKeys.FILE_PATH:      str(file_path),
                MetadataKeys.FILE_NAME:      file_path.name,
                MetadataKeys.CHUNK_TYPE:     MetadataKeys.CHUNK_TYPE_DOCUMENT,
                MetadataKeys.DOC_TYPE:       "text",
                MetadataKeys.PARSER_FALLBACK: True,
            },
        )
        splitter = SentenceSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        return splitter.get_nodes_from_documents([doc])

    # ── Private helpers ─────────────────────────────────────────
    def _convert_with_markitdown(self, file_path: Path) -> str | None:
        """
        Convert *file_path* to Markdown text using the shared MarkItDown
        instance (in-memory, REQ-06).

        Args:
            file_path: Absolute path of the source document.

        Returns:
            Non-empty Markdown string on success, or ``None`` when the
            conversion fails or produces no usable text (REQ-05).
        """
        try:
            result = self._markitdown.convert(str(file_path))
            md_text = result.text_content
            if not md_text or not md_text.strip():
                logger.warning(
                    "markitdown: empty output for %s - falling back to"
                    " SentenceSplitter",
                    file_path.name,
                )
                return None
            logger.debug(
                "markitdown: converted %s (%d chars)",
                file_path.name, len(md_text),
            )
            return md_text
        except Exception as exc:  # REQ-05: graceful degradation
            logger.warning(
                "markitdown: conversion failed for %s: %s - falling back to"
                " SentenceSplitter",
                file_path.name, exc,
            )
            return None
    def _parse_markdown(
        self, text: str, base_meta: dict[str, Any]
    ) -> list[TextNode]:
        """
        Full custom Markdown pipeline:
        1. Split by ATX headers into sections.
        2. Aggregate small sections up to self.chunk_size.
        3. Split oversized sections by paragraphs with overlap.
        """
        sections = self._split_by_headers(text)
        return self._aggregate_nodes(sections, base_meta)

    @staticmethod
    def _split_by_headers(text: str) -> list[dict[str, Any]]:
        """
        Split Markdown text on ATX header lines (# … ######).

        Returns a list of section dicts:
            level       int   — header depth (0 = before any header)
            title       str   — header text, or "Introduction"
            content     str   — full section text including the header line
            start_line  int   — 1-based
            end_line    int   — 1-based (inclusive)
        """
        lines = text.split("\n")
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] = {
            _K_LEVEL:         0,
            _K_TITLE:         "Introduction",
            _K_CONTENT_LINES: [],
            _K_START_LINE:    1,
        }

        for i, line in enumerate(lines, 1):
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                if current[_K_CONTENT_LINES]:
                    current[_K_END_LINE] = i - 1
                    current[_K_CONTENT]  = "\n".join(current.pop(_K_CONTENT_LINES))
                    sections.append(current)
                level = len(match.group(1))
                current = {
                    _K_LEVEL:         level,
                    _K_TITLE:         match.group(2).strip(),
                    _K_CONTENT_LINES: [line],
                    _K_START_LINE:    i,
                }
            else:
                current[_K_CONTENT_LINES].append(line)

        if current[_K_CONTENT_LINES]:
            current[_K_END_LINE] = len(lines)
            current[_K_CONTENT]  = "\n".join(current.pop(_K_CONTENT_LINES))
            sections.append(current)

        return sections

    def _aggregate_nodes(
        self,
        sections: list[dict[str, Any]],
        base_meta: dict[str, Any],
    ) -> list[TextNode]:
        """
        Merge consecutive sections into TextNode chunks up to MARKDOWN_CHUNK_SIZE.
        Oversized single sections are delegated to _split_large_section().
        """
        nodes: list[TextNode] = []
        bucket: list[dict[str, Any]] = []
        bucket_size = 0

        for section in sections:
            sec_size = len(section[_K_CONTENT])

            if sec_size > self.chunk_size * 1.5:
                # Flush pending bucket first
                if bucket:
                    nodes.append(self._make_node(bucket, base_meta))
                    bucket, bucket_size = [], 0
                nodes.extend(self._split_large_section(section, base_meta))
                continue

            if bucket_size + sec_size > self.chunk_size and bucket:
                nodes.append(self._make_node(bucket, base_meta))
                bucket, bucket_size = [], 0

            bucket.append(section)
            bucket_size += sec_size

        if bucket:
            nodes.append(self._make_node(bucket, base_meta))

        return nodes

    @staticmethod
    def _make_node(
        sections: list[dict[str, Any]],
        base_meta: dict[str, Any],
    ) -> TextNode:
        """Build a TextNode from an aggregated list of sections."""
        content = "\n\n".join(s[_K_CONTENT] for s in sections)
        code_blocks = re.findall(r"```[\s\S]*?```", content)

        meta = {
            **base_meta,
            # Scalar fields (ChromaDB-compatible)
            MetadataKeys.SECTION_TITLE:     sections[0][_K_TITLE],
            MetadataKeys.SECTION_LEVEL:     sections[0][_K_LEVEL],
            MetadataKeys.START_LINE:        sections[0][_K_START_LINE],
            MetadataKeys.END_LINE:          sections[-1][_K_END_LINE],
            MetadataKeys.WORD_COUNT:        len(content.split()),
            MetadataKeys.HAS_CODE_BLOCKS:   len(code_blocks) > 0,
            MetadataKeys.CODE_BLOCK_COUNT:  len(code_blocks),
            # Serialised lists → strings for ChromaDB
            MetadataKeys.SECTION_HIERARCHY: " > ".join(s[_K_TITLE] for s in sections),
            MetadataKeys.HEADER_LEVELS:     ",".join(str(s[_K_LEVEL]) for s in sections),
            # Rich Markdown metadata (REQ-MD-01..04)
            **DocumentParser._extract_rich_metadata(content),
        }
        return TextNode(id_=str(uuid.uuid4()), text=content, metadata=meta)

    @staticmethod
    def _extract_rich_metadata(content: str) -> dict[str, Any]:
        """
        Detect enriched Markdown elements in *content* and return a metadata
        dict ready to be merged into a TextNode (REQ-MD-01..04).

        Detected elements
        -----------------
        - Task-list items : ``- [ ] …`` / ``- [x] …``  (REQ-MD-01)
        - Hyperlinks      : ``[text](url)``              (REQ-MD-02)
        - Images          : ``![alt](src)``              (REQ-MD-03)
        - GFM tables      : separator row ``| --- |``    (REQ-MD-04)
        """
        # ── Images before links to avoid double-counting (REQ-MD-03) ────────
        images = re.findall(r"!\[[^\]]*\]\([^)]+\)", content)

        # ── Hyperlinks — negative lookbehind '!' to exclude images (REQ-MD-02)
        links = re.findall(r"(?<!!)\[[^\]]+\]\([^)]+\)", content)

        # ── Task-list items (REQ-MD-01) ──────────────────────────────────────
        checkboxes = re.findall(r"(?m)^[ \t]*- \[([ xX])\] ", content)
        checked    = sum(1 for c in checkboxes if c.lower() == "x")

        # ── GFM table separator rows — one per table (REQ-MD-04) ────────────
        # Pattern matches lines like: | --- | --- | --- | or | :--- | :---: | ---: |
        # Key: \s* allows flexible whitespace, \|? makes trailing pipe optional
        tables = re.findall(
            r"^\s*\|\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$",
            content,
            re.MULTILINE,
        )

        return {
            MetadataKeys.HAS_CHECKBOXES:  len(checkboxes) > 0,
            MetadataKeys.CHECKBOX_COUNT:  len(checkboxes),
            MetadataKeys.CHECKED_COUNT:   checked,
            MetadataKeys.UNCHECKED_COUNT: len(checkboxes) - checked,
            MetadataKeys.HAS_LINKS:       len(links) > 0,
            MetadataKeys.LINK_COUNT:      len(links),
            MetadataKeys.HAS_IMAGES:      len(images) > 0,
            MetadataKeys.IMAGE_COUNT:     len(images),
            MetadataKeys.HAS_TABLES:      len(tables) > 0,
            MetadataKeys.TABLE_COUNT:     len(tables),
        }

    def _split_large_section(
        self,
        section: dict[str, Any],
        base_meta: dict[str, Any],
    ) -> list[TextNode]:
        """
        Split an oversized section by paragraphs with 1-paragraph overlap.

        When a single paragraph is itself larger than chunk_size (e.g. a
        fenced code block with no internal blank lines), it is force-split
        on newline boundaries so that every resulting chunk respects the
        configured limit.
        """
        paragraphs = re.split(r"\n\s*\n", section[_K_CONTENT])
        nodes: list[TextNode] = []
        current_paras: list[str] = []
        current_size = 0

        def _flush(paras: list[str]) -> TextNode:
            chunk_text = "\n\n".join(paras)
            code_blocks = re.findall(r"```[\s\S]*?```", chunk_text)
            meta = {
                **base_meta,
                MetadataKeys.SECTION_TITLE:     section[_K_TITLE],
                MetadataKeys.SECTION_LEVEL:     section[_K_LEVEL],
                MetadataKeys.SECTION_HIERARCHY: section[_K_TITLE],
                MetadataKeys.HEADER_LEVELS:     str(section[_K_LEVEL]),
                MetadataKeys.START_LINE:        section[_K_START_LINE],
                MetadataKeys.END_LINE:          section[_K_END_LINE],
                MetadataKeys.WORD_COUNT:        len(chunk_text.split()),
                MetadataKeys.HAS_CODE_BLOCKS:   len(code_blocks) > 0,
                MetadataKeys.CODE_BLOCK_COUNT:  len(code_blocks),
                MetadataKeys.IS_PARTIAL:        True,
                # Rich Markdown metadata (REQ-MD-01..04)
                **DocumentParser._extract_rich_metadata(chunk_text),
            }
            return TextNode(id_=str(uuid.uuid4()), text=chunk_text, metadata=meta)

        def _force_split_paragraph(para: str) -> list[str]:
            """Split an oversized paragraph on newline boundaries."""
            lines = para.split("\n")
            chunks: list[str] = []
            current_lines: list[str] = []
            current_len = 0
            for line in lines:
                line_len = len(line) + 1  # +1 for the newline separator
                if current_len + line_len > self.chunk_size and current_lines:
                    chunks.append("\n".join(current_lines))
                    current_lines = [line]
                    current_len = len(line)
                else:
                    current_lines.append(line)
                    current_len += line_len
            if current_lines:
                chunks.append("\n".join(current_lines))
            return chunks

        for para in paragraphs:
            para_size = len(para)

            # If a single paragraph exceeds chunk_size, force-split it on
            # newline boundaries (handles e.g. fenced code blocks with no
            # internal blank lines).
            if para_size > self.chunk_size:
                # Flush any accumulated paragraphs first.
                if current_paras:
                    nodes.append(_flush(current_paras))
                    current_paras, current_size = [], 0
                sub_chunks = _force_split_paragraph(para)
                for sub in sub_chunks:
                    nodes.append(_flush([sub]))
                continue

            if current_size + para_size > self.chunk_size and current_paras:
                nodes.append(_flush(current_paras))
                # 1-paragraph overlap -- only when the overlap itself fits within chunk_size.
                overlap_para = current_paras[-1]
                if len(overlap_para) + para_size <= self.chunk_size:
                    current_paras = [overlap_para, para]
                else:
                    current_paras = [para]
                current_size = sum(len(p) for p in current_paras)
            else:
                current_paras.append(para)
                current_size += para_size

        if current_paras:
            nodes.append(_flush(current_paras))

        return nodes
