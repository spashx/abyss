# ingestion/embed_builder.py — Construction of embedded text with semantic header
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from llama_index.core.schema import TextNode

from ..config import EMBED_BUILDER_DEBUG, EMBED_BUILDER_DEBUG_OUTPUT_DIR
from .metadata import MetadataKeys

logger = logging.getLogger(__name__)


class EmbedBuilder:
    """
    Build the final text sent to the embedding model for each TextNode.

    For each chunk a semantic header is prepended to the raw content,
    derived from its metadata. This gives the embedding model extra context
    without relying on LlamaIndex's automatic metadata injection
    (which is disabled via excluded_embed_metadata_keys).

    Header formats by chunk_type:
    - code       → // comment block (file, symbol, SCIP info)
    - document   → [bracket tags]  (file, type, section)
    - structured → // comment block (file, json_path / xml_path)
    - other      → text returned as-is

    Debug mode (config.EMBED_BUILDER_DEBUG = True):
    One HTML file is written per source file, named <source_file>.html,
    in the directory defined by config.EMBED_BUILDER_OUTPUT_DIR.
    Columns are colour-coded by metadata category:
    - Blue   : document-level  (file_path, file_name, language, …)
    - Green  : chunk-level     (start_line, end_line, section_title, …)
    - Orange : SCIP-enriched   (symbol, kind, callers, callees, …)
    """

    def apply(self, nodes: list[TextNode]) -> None:
        """
        Build and inject the semantic header for every node (in-place).

        Also sets excluded_embed_metadata_keys to prevent LlamaIndex
        from re-injecting the same metadata a second time.

        If EMBED_BUILDER_DEBUG is True, exports one HTML report per source
        file into config.EMBED_BUILDER_OUTPUT_DIR.

        Args:
            nodes: List of TextNode produced by the parsers / SCIP enricher.
        """
        for node in nodes:
            node.text = self.build(node)
            # Prevent LlamaIndex from re-injecting metadata into the embedding text.
            node.excluded_embed_metadata_keys = list(node.metadata.keys())

        if EMBED_BUILDER_DEBUG and nodes:
            self._export_debug_html(nodes)

    def build(self, node: TextNode) -> str:
        """
        Build the enriched text for a single node.

        Args:
            node: TextNode with populated metadata.

        Returns:
            Header + original text, ready to be embedded.
        """
        chunk_type = node.metadata.get(MetadataKeys.CHUNK_TYPE, "")
        if chunk_type == MetadataKeys.CHUNK_TYPE_CODE:
            return self._build_code(node.text, node.metadata)
        elif chunk_type == MetadataKeys.CHUNK_TYPE_DOCUMENT:
            return self._build_doc(node.text, node.metadata)
        elif chunk_type == MetadataKeys.CHUNK_TYPE_STRUCTURED:
            return self._build_structured(node.text, node.metadata)
        return node.text

    # ── Debug export ──────────────────────────────────────────────────────────

    def _export_debug_html(self, nodes: list[TextNode]) -> None:
        """
        Export one HTML debug report per source file.

        Nodes are grouped by their 'file_name' metadata key.  For each
        group the output file is named '<file_name>.html' and written into
        EMBED_BUILDER_OUTPUT_DIR (created automatically if needed).

        Args:
            nodes: All enriched TextNode instances for this ingestion batch.
        """
        output_dir = Path(EMBED_BUILDER_DEBUG_OUTPUT_DIR)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "[EmbedBuilder DEBUG] Cannot create output directory %s: %s",
                output_dir, exc,
            )
            return

        # Group nodes by source file name.
        groups: dict[str, list[TextNode]] = defaultdict(list)
        for node in nodes:
            file_name = node.metadata.get(MetadataKeys.FILE_NAME, "_unknown_")
            groups[file_name].append(node)

        for file_name, file_nodes in groups.items():
            output_path = output_dir / (file_name + ".html")
            try:
                html = self._build_html_for_file(file_name, file_nodes)
                output_path.write_text(html, encoding="utf-8")
                logger.info(
                    "[EmbedBuilder DEBUG] %d chunks => %s",
                    len(file_nodes), output_path.resolve(),
                )
            except OSError as exc:
                logger.error(
                    "[EmbedBuilder DEBUG] Cannot write %s: %s",
                    output_path, exc,
                )

    def _build_html_for_file(
        self, file_name: str, nodes: list[TextNode]
    ) -> str:
        """
        Build a complete, self-contained HTML report for one source file.

        Layout
        ------
        - Sticky header with file name and chunk count.
        - Legend explaining the three column colour categories.
        - One row per chunk; metadata columns are colour-coded:
            * Blue   → document-level  (constant for the whole file)
            * Green  → chunk-level     (positional / structural)
            * Orange → SCIP-enriched   (call-graph / symbol data)
        - Last column: enriched text rendered in a monospace block.

        Args:
            file_name: Name of the source file (used in the page title).
            nodes:     All TextNode chunks that belong to this source file.

        Returns:
            Complete HTML document as a string (UTF-8).
        """
        # Collect the union of all metadata keys across all nodes for this file.
        all_keys: set[str] = set()
        for node in nodes:
            all_keys.update(node.metadata.keys())

        # Build ordered column list: grouped by category for visual clarity.
        # Order: document-level → chunk-level → SCIP-enriched
        doc_cols   = sorted(c for c in all_keys if c in MetadataKeys.DOC_LEVEL)
        scip_cols  = sorted(c for c in all_keys if c in MetadataKeys.SCIP_LEVEL)
        chunk_cols = sorted(
            c for c in all_keys
            if c not in MetadataKeys.DOC_LEVEL and c not in MetadataKeys.SCIP_LEVEL
        )
        columns = doc_cols + chunk_cols + scip_cols

        # Classify each column into one of the three categories.
        def _css_class(col: str) -> str:
            if col in MetadataKeys.DOC_LEVEL:
                return "col-doc"
            if col in MetadataKeys.SCIP_LEVEL:
                return "col-scip"
            return "col-chunk"

        chunk_count = len(nodes)

        # ── HTML head ────────────────────────────────────────────────────────
        lines: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="UTF-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f"  <title>EmbedBuilder — {self._escape_html(file_name)}</title>",
            "  <style>",
            # ── Reset & base ──
            "    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }",
            "    body {",
            "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;",
            "      font-size: 10px;",
            "      background: #f0f2f5;",
            "      color: #1a1a2e;",
            "      padding: 0;",
            "    }",
            # ── Top bar ──
            "    .topbar {",
            "      position: sticky; top: 0; z-index: 100;",
            "      background: #1a1a2e;",
            "      color: #e8ecf0;",
            "      padding: 12px 24px;",
            "      display: flex; align-items: center; gap: 16px;",
            "      box-shadow: 0 2px 8px rgba(0,0,0,0.35);",
            "    }",
            "    .topbar h1 { font-size: 1rem; font-weight: 600; letter-spacing: 0.02em; }",
            "    .topbar .badge {",
            "      background: #3a7bd5; color: white;",
            "      padding: 2px 10px; border-radius: 12px;",
            "      font-size: 0.78rem; font-weight: 600;",
            "    }",
            # ── Legend ──
            "    .legend {",
            "      display: flex; gap: 20px; align-items: center;",
            "      padding: 10px 24px;",
            "      background: #ffffff;",
            "      border-bottom: 1px solid #d0d7de;",
            "      flex-wrap: wrap;",
            "    }",
            "    .legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; }",
            "    .legend-swatch {",
            "      display: inline-block; width: 16px; height: 16px;",
            "      border-radius: 3px; flex-shrink: 0;",
            "    }",
            # ── Table wrapper ──
            "    .table-wrap { overflow-x: auto; padding: 16px 24px 40px; }",
            # ── Table ──
            "    table {",
            "      width: 100%; border-collapse: collapse;",
            "      background: white;",
            "      box-shadow: 0 1px 4px rgba(0,0,0,0.10);",
            "      border-radius: 6px;",
            "      overflow: hidden;",       
            "    }",
            "    thead tr { background: #1a1a2e; color: #e8ecf0; }",
            "    th {",
            "      padding: 10px 12px;",
            "      text-align: left;",
            "      font-size: 0.78rem;",
            "      font-weight: 700;",
            "      letter-spacing: 0.04em;",
            "      text-transform: uppercase;",
            "      white-space: nowrap;",
            "      border-right: 1px solid rgba(255,255,255,0.08);",
            "    }",
            "    td {",
            "      padding: 8px 12px;",
            "      border-bottom: 1px solid #e8ecf0;",
            "      border-right: 1px solid #f0f2f5;",
            "      vertical-align: top;",
            "      font-family: 'SFMono-Regular', 'Cascadia Code', 'Fira Code', Menlo, Consolas, monospace;",
            "      font-size: 0.78rem;",
            "      line-height: 1.5;",
            "      word-break: break-word;",
            "      overflow-wrap: break-word;",
            "    }",
            "    tbody tr:hover td { background: #fafbfc !important; }",
            # ── Row index ──
            "    td.row-idx {",
            "      color: #888; font-size: 0.75rem;",
            "      text-align: right; white-space: nowrap;",
            "      background: #f6f8fa;",
            "    }",
            "    th.row-idx { background: #111827; }",
            # ── Category: document-level ──
            "    th.col-doc { background: #1a4480; }",
            "    td.col-doc {",
            "      background: #eef4ff;",
            "      color: #1a3a5c;",
            "      border-right: 1px solid #c8d8f0;",
            "      max-width: 200px;",
            "    }",
            # ── Category: chunk-level ──
            "    th.col-chunk { background: #1a5c34; }",
            "    td.col-chunk {",
            "      background: #edfaef;",
            "      color: #1a4a2a;",
            "      border-right: 1px solid #b8e0c4;",
            "      max-width: 260px;",
            "    }",
            # ── Category: SCIP-enriched ──
            "    th.col-scip { background: #7d3c00; }",
            "    td.col-scip {",
            "      background: #fff7ee;",
            "      color: #5c2e00;",
            "      border-right: 1px solid #f0d0a0;",
            "      max-width: 260px;",
            "    }",
            # ── Enriched text column ──
            "    th.col-text { background: #333; }",
            "    td.col-text {",
            "      white-space: pre-wrap;",
            "      background: #fafafa;",
            "      color: #24292e;",
            "      line-height: 1.55;",
            "      min-width: 520px;",
            "      width: 40%;",
            "    }",
            "  </style>",
            "</head>",
            "<body>",
        ]

        # ── Top bar ──────────────────────────────────────────────────────────
        lines += [
            "  <div class=\"topbar\">",
            f"    <h1>&#128269; EmbedBuilder Debug — {self._escape_html(file_name)}</h1>",
            f"    <span class=\"badge\">{chunk_count} chunk{'s' if chunk_count != 1 else ''}</span>",
            "  </div>",
        ]

        # ── Legend ───────────────────────────────────────────────────────────
        lines += [
            "  <div class=\"legend\">",
            "    <strong style=\"font-size:0.8rem;\">Metadata categories:</strong>",
            "    <span class=\"legend-item\">",
            "      <span class=\"legend-swatch\" style=\"background:#1a4480\"></span>",
            "      Document-level (file, language, type\u2026)",
            "    </span>",
            "    <span class=\"legend-item\">",
            "      <span class=\"legend-swatch\" style=\"background:#1a5c34\"></span>",
            "      Chunk-level (position, section, structure\u2026)",
            "    </span>",
            "    <span class=\"legend-item\">",
            "      <span class=\"legend-swatch\" style=\"background:#7d3c00\"></span>",
            "      SCIP-enriched (symbol, kind, callers, callees…)",
            "    </span>",
            "  </div>",
        ]

        # ── Table ────────────────────────────────────────────────────────────
        lines.append("  <div class=\"table-wrap\">")
        lines.append("  <table>")
        lines.append("    <thead><tr>")
        lines.append('      <th class="row-idx">#</th>')

        # Column headers — colour-coded by category.
        for col in columns:
            css = _css_class(col)
            lines.append(f'      <th class="{css}">{self._escape_html(col)}</th>')
        lines.append('      <th class="col-text">enriched_text</th>')
        lines.append("    </tr></thead>")

        lines.append("    <tbody>")
        for idx, node in enumerate(nodes, start=1):
            lines.append("      <tr>")
            lines.append(f'        <td class="row-idx">{idx}</td>')

            # Metadata cells — colour per category.
            for col in columns:
                css = _css_class(col)
                raw = node.metadata.get(col, "")
                val = self._escape_html(str(raw).strip())
                lines.append(f'        <td class="{css}">{val}</td>')

            # Enriched text cell.
            lines.append(f'        <td class="col-text">{self._escape_html(node.text)}</td>')
            lines.append("      </tr>")

        lines += [
            "    </tbody>",
            "  </table>",
            "  </div>",  # .table-wrap
            "</body>",
            "</html>",
        ]

        return "\n".join(lines)

    # ── HTML helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape the five HTML special characters to safe entity references."""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
        )

    # ── Private header builders ───────────────────────────────────────────────

    def _build_code(self, code: str, meta: dict) -> str:
        """
        Build the semantic header for a code chunk.

        The header is a C-style comment block summarising the symbol
        and its SCIP call-graph context (if available).

        Example output:
            // File     : src/Orders/OrderService.cs
            // Language : csharp
            // Symbol   : OrderService#ValidateOrder()
            // Kind     : method
            // In       : OrderService
            // Summary  : Validates an order before submission.
            // Calls    : PriceCalculator#Compute(), InventoryService#Check()
            // Called by: OrderController#Post()
        """
        header: list[str] = []

        if v := meta.get(MetadataKeys.FILE_NAME):
            header.append(f"// File     : {v}")
        if v := meta.get(MetadataKeys.LANGUAGE):
            header.append(f"// Language : {v}")
        if v := meta.get(MetadataKeys.DISPLAY_NAME):
            header.append(f"// Symbol   : {v}")
        if v := meta.get(MetadataKeys.KIND):
            header.append(f"// Kind     : {v}")
        if v := meta.get(MetadataKeys.ENCLOSING):
            # Keep only the last component of the qualified name.
            short = v.rstrip("#").rstrip(".").split("/")[-1].split("#")[-1]
            if short:
                header.append(f"// In       : {short}")
        if v := meta.get(MetadataKeys.DOCUMENTATION):
            first_line = v.split("\n")[0].strip()
            if first_line:
                header.append(f"// Summary  : {first_line}")
        if v := meta.get(MetadataKeys.CALLEES):
            header.append(f"// Calls    : {self._shorten_scip_symbols(v)}")
        if v := meta.get(MetadataKeys.CALLERS):
            header.append(f"// Called by: {self._shorten_scip_symbols(v)}")

        return ("\n".join(header) + "\n\n" + code) if header else code

    def _build_doc(self, text: str, meta: dict) -> str:
        """
        Build the semantic header for a document chunk.

        Uses bracket-tag notation to preserve readability alongside
        natural-language content.
        """
        header: list[str] = []

        if v := meta.get(MetadataKeys.FILE_NAME):
            header.append(f"[Document: {v}]")
        if v := meta.get(MetadataKeys.DOC_TYPE):
            header.append(f"[Type: {v}]")
        if v := meta.get(MetadataKeys.SECTION_TITLE):
            level = meta.get(MetadataKeys.SECTION_LEVEL, 1)
            header.append(f"[Section: {'#' * level} {v}]")

        return (" ".join(header) + "\n\n" + text) if header else text

    def _build_structured(self, text: str, meta: dict) -> str:
        """Build the semantic header for a JSON / XML chunk."""
        header: list[str] = []

        if v := meta.get(MetadataKeys.FILE_NAME):
            header.append(f"// File: {v}")
        if v := meta.get(MetadataKeys.JSON_PATH):
            header.append(f"// JSON Path: {v}")
        if v := meta.get(MetadataKeys.XML_PATH):
            header.append(f"// XML Path: {v}")

        return ("\n".join(header) + "\n\n" + text) if header else text

    @staticmethod
    def _shorten_scip_symbols(symbols_str: str) -> str:
        """
        Shorten a comma-separated list of SCIP symbol identifiers.

        Keeps only the local part of each qualified name and limits
        the output to the first five entries.

        Example:
            'csharp . Orders/PriceCalculator#Compute().'
            → 'PriceCalculator#Compute()'
        """
        parts = [s.strip() for s in symbols_str.split(",")]
        short: list[str] = []
        for part in parts[:5]:  # cap at 5 to avoid very long headers
            cleaned = part.rstrip(".")
            if "/" in cleaned:
                cleaned = cleaned.split("/", 1)[-1]
            cleaned = cleaned.replace(" ", "")
            short.append(cleaned)
        return ", ".join(short)
