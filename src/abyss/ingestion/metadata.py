# ingestion/metadata.py — Centralised metadata key names for TextNode
"""
Single source of truth for all metadata key names and discriminator values
used across the ingestion pipeline.

Every parser, enricher, and consumer imports ``MetadataKeys`` from this module
instead of scattering hard-coded string literals across the codebase.

Usage
-----
    from .metadata import MetadataKeys          # from inside ingestion/
    from ..metadata import MetadataKeys         # from inside ingestion/parsers/

    node.metadata[MetadataKeys.FILE_NAME]
    node.metadata.get(MetadataKeys.CHUNK_TYPE) == MetadataKeys.CHUNK_TYPE_CODE
"""
from __future__ import annotations


class MetadataKeys:
    """
    All metadata key names and chunk-type discriminator values used in TextNode.

    Sections
    --------
    File-level keys
        Constant for every chunk produced from the same source file.
    Chunk-level keys
        Positional / structural data specific to each individual chunk.
    Markdown / document section keys
        Section hierarchy and content statistics for Markdown documents.
    JSON structured keys
        Structural metadata for JSON file chunks.
    XML structured keys
        Structural metadata for XML file chunks.
    SCIP-enriched keys
        Call-graph and symbol data injected by ScipEnricher (optional).
    Chunk-type values
        Allowed values for the CHUNK_TYPE key.
    Category sets
        Pre-built frozensets for HTML debug-report colour-coding.
    """

    # ── File-level keys ───────────────────────────────────────────────────────
    # These keys carry the same value for every chunk produced from one file.

    FILE_PATH         = "file_path"       # absolute path of the source file
    FILE_NAME         = "file_name"       # file name with extension (e.g. "server.py")
    LANGUAGE          = "language"        # language name (e.g. "csharp", "python", "json")
    DOC_TYPE          = "doc_type"        # document extension without dot (e.g. "md", "pdf")
    CHUNK_TYPE        = "chunk_type"      # discriminator — see CHUNK_TYPE_* constants below
    PARSER_FALLBACK   = "parser_fallback" # True when DocumentParser used its plain-text fallback
    MARKITDOWN_CONVERTED = "markitdown_converted" # True when converted from non-MD via markitdown
    ORIGINAL_DOC_TYPE    = "original_doc_type"    # original ext without dot (e.g. "pdf", "pptx")

    # ── Chunk-level positional keys ───────────────────────────────────────────

    START_LINE = "start_line"   # 1-based start line of the chunk in the source file
    END_LINE   = "end_line"     # 1-based end line of the chunk in the source file
    IS_PARTIAL = "is_partial"   # True for sub-chunks from oversized-element splits

    # ── Markdown / document section keys ─────────────────────────────────────

    SECTION_TITLE     = "section_title"      # ATX header text of the leading section
    SECTION_LEVEL     = "section_level"      # header depth (1 = h1 … 6 = h6)
    SECTION_HIERARCHY = "section_hierarchy"  # " > " joined title chain of merged sections
    HEADER_LEVELS     = "header_levels"      # comma-separated levels of merged sections
    HAS_CODE_BLOCKS   = "has_code_blocks"    # True when the chunk contains fenced code
    CODE_BLOCK_COUNT  = "code_block_count"   # number of fenced code blocks in the chunk
    WORD_COUNT        = "word_count"         # rough word count of the chunk text

    # ── Markdown rich-content metadata (REQ-MD-01 à REQ-MD-04) ─────────────

    HAS_CHECKBOXES   = "has_checkboxes"    # True if the chunk contains task-list items
    CHECKBOX_COUNT   = "checkbox_count"    # total number of task items (checked + unchecked)
    CHECKED_COUNT    = "checked_count"     # number of checked items (- [x])
    UNCHECKED_COUNT  = "unchecked_count"   # number of unchecked items (- [ ])
    HAS_LINKS        = "has_links"         # True if the chunk contains hyperlinks [text](url)
    LINK_COUNT       = "link_count"        # number of hyperlinks
    HAS_IMAGES       = "has_images"        # True if the chunk contains images ![alt](src)
    IMAGE_COUNT      = "image_count"       # number of images
    HAS_TABLES       = "has_tables"        # True if the chunk contains GFM tables
    TABLE_COUNT      = "table_count"       # number of GFM tables

    # ── JSON structured keys ──────────────────────────────────────────────────

    JSON_PATH  = "json_path"  # dot-notation path  (e.g. "$.users" or "$")
    JSON_KEY   = "json_key"   # top-level key name (single-key chunks only)
    JSON_KEYS  = "keys"       # comma-separated key names in multi-key chunks
    JSON_TYPE  = "json_type"  # Python type name of the value ("dict", "list", …)
    IS_ARRAY   = "is_array"   # serialised bool — "True"/"False" (ChromaDB compatible)
    IS_OBJECT  = "is_object"  # serialised bool — "True"/"False" (ChromaDB compatible)

    # ── XML structured keys ───────────────────────────────────────────────────

    XML_PATH        = "xml_path"         # slash-delimited path (e.g. "/root/ItemGroup")
    XML_TAG         = "xml_tag"          # local tag name of the element
    XML_ROOT        = "xml_root"         # local tag name of the document root element
    TAG_COUNT       = "tag_count"        # number of XML elements in this chunk
    CHILD_COUNT     = "child_count"      # direct children of the element
    IS_GROUPED      = "is_grouped"       # True when the chunk is a pre-grouped element batch
  

    # ── SCIP-enriched keys ────────────────────────────────────────────────────
    # Injected by ScipEnricher.enrich() after parsing.
    # These keys are absent when no SCIP index is available.

    SYMBOL        = "symbol"        # fully-qualified SCIP symbol identifier
    DISPLAY_NAME  = "display_name"  # human-readable symbol name
    KIND          = "kind"          # symbol kind ("method", "class", "function", …)
    ENCLOSING     = "enclosing"     # qualified name of the enclosing symbol
    DOCUMENTATION = "documentation" # docstring / XML-doc comment extracted by SCIP
    CALLERS       = "callers"       # comma-separated list of caller symbol names
    CALLEES       = "callees"       # comma-separated list of callee symbol names

    # ── Chunk-type discriminator values ───────────────────────────────────────
    # Allowed values for the CHUNK_TYPE key.

    CHUNK_TYPE_CODE            = "code"
    CHUNK_TYPE_DOCUMENT        = "document"
    CHUNK_TYPE_STRUCTURED      = "structured"
    CHUNK_TYPE_JSON_SPLIT      = "json_split"
    CHUNK_TYPE_JSON_ARRAY_SPLIT = "json_array_split"
    CHUNK_TYPE_XML_SPLIT       = "xml_split"

    # ── Category sets ─────────────────────────────────────────────────────────
    # Pre-built frozensets used for HTML debug-report column colour-coding.
    # Note: class-body name lookup is sequential, so referencing earlier
    # class attributes here is valid in standard Python.

    #: Keys that carry document-level information (constant per source file).
    DOC_LEVEL: frozenset = frozenset({
        FILE_PATH, FILE_NAME, LANGUAGE, DOC_TYPE,
        CHUNK_TYPE, PARSER_FALLBACK,
    })

    #: Keys injected exclusively by the SCIP enricher (call-graph / symbol data).
    SCIP_LEVEL: frozenset = frozenset({
        SYMBOL, DISPLAY_NAME, KIND, ENCLOSING,
        DOCUMENTATION, CALLERS, CALLEES,
    })
