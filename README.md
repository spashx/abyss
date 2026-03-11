<div align="center">

```
    ___    ____  __  _______ _____
   /   |  / __ \\ \/ / ___// ___/
  / /| | / __  | \  /\__ \ \__ \
 / ___ |/ /_/ / / / ___/ /___/ /
/_/  |_/_____/ /_/ /____//____/
```

**Local-first RAG engine for codebases and documentation**

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-%20%20GNU%20GPLv3%20-blue)](#license)
[![Offline](https://img.shields.io/badge/runs-100%25%20offline-brightgreen)](#)
[![No GPU](https://img.shields.io/badge/GPU-not%20required-orange)](#)

</div>

---

Abyss is an all-in-one **Retrieval-Augmented Generation (RAG)** server that indexes your source code and documentation locally, then exposes semantic search through the **Model Context Protocol (MCP)**. It is designed for developers and software architects who need accurate, context-aware code search directly in their AI-assisted workflow — without sending data to external services.

- **100% offline** — no cloud API, no telemetry, no data leaves your machine
- **No GPU required** — runs efficiently on CPU with a quantized sentence-transformers model
- **MCP-native** — integrates directly into VS Code, Claude Desktop, and any MCP-compatible client
- **Multi-language** — indexes source code, structured files, and office documents in a unified vector database

---

## How to get started. Quicky 🚀

see [Installation](#installation)


## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Supported File Types](#supported-file-types)
- [Ingestion Pipeline](#ingestion-pipeline)
- [Installation](#installation)
- [Preparing a Directory for Ingestion](#preparing-a-directory-for-ingestion)
- [MCP Server Setup (VS Code)](#mcp-server-setup-vs-code)
- [Available MCP Tools](#available-mcp-tools)
- [Configuration Reference](#configuration-reference)
- [Optional: SCIP Source Code Enrichment](#optional-scip-source-code-enrichment)
- [Debugging the Embedding Process](#debugging-the-embedding-process)

---

## Features

| Feature | Detail |
|---------|--------|
| **Semantic search** | Vector similarity search over code and documentation |
| **Multi-language code parsing** | Syntax-aware AST chunking via Tree-sitter |
| **Document ingestion** | Universal document conversion (PDF, DOCX, PPTX, images…) |
| **SCIP enrichment** | Optional caller/callee graph indexing for deep code navigation |
| **Local embeddings** | HF `all-MiniLM-L6-v2` by default. downloaded once, cached, never re-downloaded |
| **Persistent storage** | ChromaDB SQLite database — survives restarts |
| **MCP interface** | 8 tools + 3 resources accessible from any MCP client |
| **Advanced filtering** | Filter results by language, kind, file path, line range, text |
| **Debug mode** | Per-file HTML reports showing chunks, metadata, and semantic headers |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Orchestration** | [LlamaIndex](https://www.llamaindex.ai/) (`llama-index-core`) |
| **Code parsing** | [Tree-sitter](https://tree-sitter.github.io/) + `tree-sitter-language-pack` |
| **SCIP indexing** | [SCIP protocol](https://scip-code.org/) (optional, add code intelligence metadata to your code chunks) |
| **Document conversion** | [MarkItDown](https://github.com/microsoft/markitdown) (Microsoft) |
| **Embeddings** | [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). Customizable in config.yaml |
| **Vector database** | [ChromaDB](https://www.trychroma.com/) (embedded SQLite, no external server) |
| **Configuration** | YAML (`config.yaml`) with Python fallback defaults |
| **Runtime** | Python 3.13, managed with [uv](https://github.com/astral-sh/uv) |

---

## Supported File Types

### Source Code — Tree-sitter Parsers

Tree-sitter provides **syntax-aware AST parsing**, chunking code at meaningful syntactic boundaries (functions, classes, methods) rather than arbitrary line counts.

| Extension | Language | Tree-sitter Grammar |
|-----------|----------|-------------------|
| `.cs` | C# | `csharp` |
| `.py` | Python | `python` |
| `.java` | Java | `java` |
| `.ts` / `.tsx` | TypeScript / TSX | `typescript` |
| `.js` / `.jsx` | JavaScript / JSX | `javascript` |
| `.html` / `.htm` | HTML | `html` |

> Additional languages can be added in `config.yaml` under `code_extensions` as long as Tree-sitter supports the grammar.

### Documents — MarkItDown Converters

All documents are converted to Markdown first using [MarkItDown](https://github.com/microsoft/markitdown), then chunked by section headers when possible.

| Format | Extensions |
|--------|-----------|
| Markdown | `.md` |
| Plain text / RST | `.txt`, `.rst` |
| PDF | `.pdf` |
| Office documents | `.docx`, `.pptx`, `.xlsx` |
| e-Books | `.epub` |
| Notebooks | `.ipynb` |
| Tabular data | `.csv` |
| Images (OCR) | `.png`, `.jpg`, `.jpeg` |

### Structured Files — Dedicated Parsers

| Format | Extensions | Parser strategy |
|--------|-----------|----------------|
| JSON | `.json` | Per-key / per-array-group units, then merged up to chunk size |
| XML / MSBuild | `.xml`, `.csproj`, `.props`, `.config` | Per-child-element units; project files always as single chunk |

---

## Ingestion Pipeline

The ingestion pipeline transforms raw files into searchable vector chunks through five sequential stages:

```
 ┌───────────────┐
 │ File Discovery│  discover() — recursive glob, size filter (max 10MB),
 │               │  exclude dirs/extensions, classify by type
 └──────┬────────┘
        │ file list
        ▼
 ┌───────────────┐
 │    Parsing    │  Dispatch by file type:
 │               │  CODE     → CodeParser  (Tree-sitter AST splitter)
 │               │  .json    → JsonParser  (key/array group units)
 │               │  .xml     → XmlParser   (element group units)
 │               │  DOCUMENT → DocParser   (header sections + MarkItDown)
 │               │  UNKNOWN  → DocParser fallback (SentenceSplitter)
 └──────┬────────┘
        │ TextNodes with metadata
        ▼
 ┌───────────────┐
 │SCIP Enrichment│  (optional) Matches chunks to SCIP index by file+line
 │               │  Injects: symbol, kind, display_name, enclosing,
 │               │  documentation, callers[], callees[]
 └──────┬────────┘
        │ enriched TextNodes
        ▼
 ┌───────────────┐
 │  EmbedBuilder │  Prepends a semantic header to each chunk's text:
 │               │
 │               │  // File     : src/Orders/OrderService.cs
 │               │  // Language : csharp
 │               │  // Symbol   : ValidateOrder
 │               │  // Kind     : method
 │               │  // Calls    : PriceCalculator#Compute()
 │               │  // Called by: OrderController#Post()
 │               │  <original chunk text>
 └──────┬────────┘
        │ semantically-enriched text
        ▼
 ┌───────────────┐
 │  Embedding    │  Batch encode enriched text with all-MiniLM-L6-v2
 │  & Storage    │  Upsert into ChromaDB (cosine similarity collection)
 │               │  Register file in DocumentRegistry (hash, size, timestamp)
 └───────────────┘
```

### Parser Details

#### 🟡 DocumentParser — **Recommended for most non-code content**

The **DocumentParser** is the most sophisticated and flexible parser in Abyss. It handles:

- **Native Markdown** (`.md`, `.rst`, `.txt`)
- **Universal document formats** (PDF, DOCX, PPTX, XLSX, EPUB, images via OCR)
- **Fallback for unknown file types** (any unrecognized extension)

**Processing pipeline:**

1. **Document Identification & Conversion**
   - If not Markdown: MarkItDown converts to Markdown (preserves structure, extracts tables, lists, embedded images)
   - If Markdown: used as-is
   - Result: Consistent Markdown intermediate representation

2. **Header-Based Section Detection**
   - Splits on ATX headers (`# H1`, `## H2`, `### H3`, etc.)
   - Preserves section hierarchy as metadata (`section_title`, `section_level`, `section_hierarchy`)
   - Example: A section under `## Configuration` nested in `# Setup` records: `section_hierarchy: ["Setup", "Configuration"]`

3. **Rich Metadata Extraction**
   - `word_count` — tokens in section
   - `has_code_blocks`, `code_block_count` — Markdown fenced code (` ``` `)
   - `has_links`, `link_count` — `[text](url)` references
   - `has_images`, `image_count` — `![alt](src)` references
   - `has_tables`, `table_count` — pipe-delimited table rows
   - `has_checkboxes`, `checkbox_count`, `checked_count` — task lists

4. **Fallback: Sentence Splitting**
   - If no headers found, falls back to sentence-level splitting
   - Maintains `word_count` metadata per sentence

**Example output from a README:**

```yaml
File: README.md
├─ Chunk 1: "# Introduction\nAbyss is a RAG engine..."
│  └─ Metadata:
│     - section_title: "Introduction"
│     - section_level: 1
│     - word_count: 245
│     - code_block_count: 0
│     - link_count: 3
│
├─ Chunk 2: "## Installation\nRun the setup script..."
│  └─ Metadata:
│     - section_title: "Installation"
│     - section_level: 2
│     - section_hierarchy: ["Installation"]
│     - word_count: 512
│     - code_block_count: 2
│     - code_block_languages: ["powershell", "bash"]
│     - checkbox_count: 3
│     - checked_count: 1
│
└─ Chunk 3: "### Windows Setup\n```powershell\n..."
   └─ Metadata:
      - section_title: "Windows Setup"
      - section_level: 3
      - section_hierarchy: ["Installation", "Windows Setup"]
      - word_count: 189
      - code_block_count: 1
```

**Why DocumentParser excels:**
- Handles **any document format** transparently (MarkItDown abstracts away format differences)
- Leverages **semantic structure** (headers) for intelligent chunking
- Extracts **rich contextual metadata** (tables, links, code examples)
- Preserves **section hierarchy** for navigation and filtering
- Gracefully degrades to sentence splitting if no structure found

---

#### CodeParser (Tree-sitter)

Uses `CodeSplitter` from LlamaIndex with tree-sitter language grammars. Chunks are aligned to **syntactic boundaries** rather than arbitrary line counts:

- **C#**: methods, properties, classes, interfaces, enums
- **Python**: functions, classes, decorators
- **Java**: methods, nested classes, interfaces
- **TypeScript/JavaScript**: functions, arrow functions, classes, methods
- **HTML**: block elements, semantic sections

Each chunk carries precise metadata:
- `start_line` / `end_line` — source location (1-indexed)
- `chunk_type: "code"` — classifier for filtering
- (Optional with SCIP) `symbol`, `kind`, `callers[]`, `callees[]`

**Falls back to sentence-level splitting** if the language is unavailable or parsing fails.

**Example — C# method chunking:**

```csharp
// Input: OrderService.cs
public class OrderService 
{
    public async Task<Order> ProcessPayment(string orderId)  // Chunk 1: lines 5-18
    {
        var order = await _repo.Get(orderId);
        var result = await _processor.Charge(order.Amount);
        return order;
    }

    public void ValidateOrder(Order order)  // Chunk 2: lines 20-35
    {
        if (order.Items.Count == 0) throw new InvalidOperationException();
        // ...
    }
}
```

**SCIP Enrichment** — Code chunks can be further enriched with advanced metadata by pairing them with a SCIP index. See [Optional: SCIP Source Code Enrichment](#optional-scip-source-code-enrichment) to learn how SCIP indexes add caller/callee relationships, symbol kinds, and documentation to each chunk.

---

#### JsonParser

Hierarchically decomposes JSON structure:

1. **Unit extraction** — Top-level dictionary keys become individual units; large arrays grouped into batches of 50
2. **Unit merging** — Small adjacent units merged to reach target chunk size
3. **Path recording** — Each chunk stores `json_path` (e.g., `$.endpoints[0].handlers`)

Metadata per chunk:
- `json_path` — location in JSON tree
- `json_type` — `"object"`, `"array"`, `"string"`, `"number"`
- `is_array` / `is_object` — type flags
- `child_count` — immediate children

**Example:**
```json
{
  "server": {
    "endpoints": [
      {"path": "/api/users", "method": "GET"},
      {"path": "/api/users", "method": "POST"}
    ],
    "middleware": ["cors", "auth"]
  }
}
```
→ Produces chunks with `json_path` values like `$.server.endpoints`, `$.server.middleware`

---

#### XmlParser

Similar unit-merge strategy as JsonParser, but for XML element trees:

- Per-element units extracted from the tree
- Small units merged up to chunk size
- Path recorded as XPath-like notation (e.g., `/root/config/database`)

Metadata per chunk:
- `xml_path` — element location
- `xml_tag` — element name
- `tag_count` — total tags in chunk
- `child_count` — immediate children
- `is_grouped` — merged from multiple units

---

## Installation

### Prerequisites

- **Python 3.13** (managed by `uv`)
- **[uv](https://github.com/astral-sh/uv)** — fast Python package manager

Install `uv` if not already available:

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup

1. **Clone the repository**

```bash
git clone https://github.com/<your-org>/abyss.git
cd abyss
```

2. **Run the setup script** (Windows PowerShell)

```powershell
.\install-deps-for-dev.ps1
```

This script will:
- Create a Python 3.13 virtual environment at `.venv/`
- Install all dependencies from `requirements.txt` using `uv`
- Print the `mcp.json` configuration block you need to add to your MCP client

On first run, Abyss downloads the `all-MiniLM-L6-v2` embedding model (~90MB) and caches it in `data/models/`. Subsequent starts are fully offline.

### Manual Setup (macOS / Linux)

```bash
uv venv .venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt
```

---

## Preparing a Directory for Ingestion

Abyss indexes everything it finds under the target directory. Before indexing, take a few minutes to configure exclusions to avoid ingesting irrelevant or noisy files.

### Default Exclusions

The following directories are **always skipped** out of the box:

```
node_modules  .git     .svn      .hg       bin       obj
dist          build    .vs       .idea     __pycache__ .mypy_cache
.pytest_cache venv     .venv     .github   .vscode   Debug   Release
```

The following file extensions are **always excluded** (binary/compiled):

```
.bin  .exe  .dll  .obj  .pdb
```

### Customising Exclusions via `config.yaml`

Add project-specific exclusions before indexing:

```yaml
# config.yaml

exclude_dirs:
  - node_modules
  - .git
  - migrations          # exclude auto-generated DB migrations
  - TestResults         # exclude test output
  - coverage            # exclude code coverage reports

exclude_extensions:
  - ".bin"
  - ".min.js"           # exclude minified JavaScript bundles
  - ".g.cs"             # exclude Roslyn source generators output
  - ".designer.cs"      # exclude WinForms designer files
  - ".generated.ts"     # exclude API client generated code
```

### Per-Indexation Filtering

The `index_directory` MCP tool also accepts inline filters without modifying `config.yaml`:

```json
{
  "path": "D:/repos/MyProject",
  "include_extensions": [".cs", ".md"],
  "exclude_extensions": [".g.cs", ".designer.cs"]
}
```

### Practical Tips

| Scenario | Recommendation |
|----------|---------------|
| Large monorepos | Index sub-projects separately with targeted `include_extensions` |
| JavaScript/TypeScript | Add `node_modules` and `dist` to `exclude_dirs`; exclude `.min.js` and `.map` |
| .NET projects | Exclude `bin`, `obj`, `.g.cs`, `.designer.cs` |
| Python projects | Exclude `__pycache__`, `.venv`, `*.pyc` |
| Documentation-only indexing | Use `include_extensions: [".md", ".rst", ".txt"]` |

---

## MCP Server Setup (VS Code)

### 1. Configure `mcp.json`

Create or edit the MCP configuration file for VS Code. Replace `<local_repos_path>` with the **absolute path** to the cloned repository.

**Windows** — create `.vscode/mcp.json` in your workspace (or user-level `settings.json`):

```json
{
  "servers": {
    "abyss": {
      "command": "<local_repos_path>\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "abyss"
      ],
      "env": {
        "PYTHONPATH": "<local_repos_path>\\src"
      }
    }
  }
}
```

**macOS / Linux:**

```json
{
  "servers": {
    "abyss": {
      "command": "<local_repos_path>/.venv/bin/python",
      "args": [
        "-m",
        "abyss"
      ],
      "env": {
        "PYTHONPATH": "<local_repos_path>/src"
      }
    }
  }
}
```

### 2. Optional: Override the Database Path

By default, Abyss stores its database at `data/chroma_db` relative to the working directory. This can be changed into the config.yaml file.


### 3. Verify the Setup

Once the MCP server is running, use the `rag://status` resource to confirm everything is healthy:

```json
{
  "server": "abyss",
  "version": "0.2",
  "status": "ok",
  "persist_dir": "data/chroma_db",
  "total_documents": 0,
  "total_chunks": 0
}
```

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `index_directory` | Recursively index a directory. Accepts `include_extensions` and `exclude_extensions` to scope ingestion. |
| `list_documents` | List all indexed files with metadata: name, date, size, chunk count. Shows **which files** are indexed. |
| `remove_document` | Remove a file and all its chunks from the database (source file on disk is untouched). |
| `replace_document` | Re-index a single file after it has been modified on disk. |
| `clear_database` | Permanently erase all chunks and the document registry. Requires `confirm: true`. |
| `query` | Semantic search with advanced filters (language, kind, file path, line range, text). |
| `list_sources` | List unique metadata values in database: file paths, languages, kinds, chunk types. Use before querying to know **available filter values**. |
| `list_filterable_fields` | Describe all filterable metadata fields with types, operators, and examples. |

### Examples: list_documents vs list_sources

**`list_documents`** — Shows indexed files:
```json
{
  "status": "ok",
  "total_documents": 3,
  "total_chunks": 45,
  "documents": [
    {
      "file_path": "/home/user/MyApp/src/OrderService.cs",
      "file_name": "OrderService.cs",
      "indexed_at": "2026-03-11T14:32:00Z",
      "file_size": 12450,
      "chunk_count": 12
    },
    {
      "file_path": "/home/user/MyApp/src/PaymentProcessor.py",
      "file_name": "PaymentProcessor.py",
      "indexed_at": "2026-03-11T14:31:00Z",
      "file_size": 8932,
      "chunk_count": 8
    }
  ]
}
```

**`list_sources`** — Shows unique values for filtering:
```json
{
  "status": "ok",
  "sources": [
    "/home/user/MyApp/src/OrderService.cs",
    "/home/user/MyApp/src/PaymentProcessor.py",
    "/home/user/MyApp/README.md"
  ],
  "available_languages": ["csharp", "python", "markdown"],
  "available_kinds": ["class", "method", "function", "property"],
  "available_chunk_types": ["code", "document"]
}
```

**Use case:**
- **`list_documents`** → "How many files have I indexed? What's the breakdown?"
- **`list_sources`** → "Before I query, what languages/kinds exist? What values can I filter by?"

### Query Filters

The `query` tool accepts a `filters` object to narrow results:

```json
{
  "question": "how is the payment processed?",
  "top_k": 8,
  "filters": {
    "languages": ["csharp"],
    "kinds": ["method", "class"],
    "file_path_contains": "Payment",
    "line_min": 1,
    "line_max": 500,
    "must_contain": "transaction"
  }
}
```

| Filter | Type | Description |
|--------|------|-------------|
| `sources` | `string[]` | Exact file paths (from `list_sources`) |
| `languages` | `string[]` | e.g. `["csharp", "python"]` |
| `kinds` | `string[]` | SCIP symbol kind: `"method"`, `"class"`, `"property"`, `"field"`, … |
| `chunk_types` | `string[]` | `"code"`, `"document"`, `"structured"` |
| `file_path_contains` | `string` | Substring match on the file path |
| `line_min` / `line_max` | `integer` | Restrict to a line range |
| `must_contain` | `string` | Full-text substring that must be present in the chunk |

### Query Examples

**Example 1: Find all methods in C# related to "validate"**
```json
{
  "question": "validate input",
  "top_k": 10,
  "filters": {
    "languages": ["csharp"],
    "kinds": ["method"]
  }
}
```

**Example 2: Search only documentation and README files**
```json
{
  "question": "how to install dependencies",
  "top_k": 5,
  "filters": {
    "chunk_types": ["document"],
    "must_contain": ".md"
  }
}
```

**Example 3: Find payment-related code in a specific file path**
```json
{
  "question": "payment processing logic",
  "top_k": 8,
  "filters": {
    "file_path_contains": "src/Payment",
    "languages": ["csharp", "python"]
  }
}
```

**Example 4: Search within a specific line range of a file**
```json
{
  "question": "authentication token validation",
  "top_k": 6,
  "filters": {
    "sources": ["src/Auth/AuthService.cs"],
    "line_min": 50,
    "line_max": 200
  }
}
```

### MCP Resources

| URI | Description |
|-----|-------------|
| `rag://status` | Server health, document/chunk counts, last indexation summary |
| `rag://supported-extensions` | All indexed file types grouped by parser |
| `rag://stats` | Breakdown of indexed content by language, kind, and chunk type |

---

## Configuration Reference

All settings are controlled by `config.yaml` at the repository root. Missing keys fall back to built-in defaults automatically.

### File Extension Mapping

```yaml
# Source code: extension → Tree-sitter language name
code_extensions:
  ".cs": csharp
  ".py": python
  ".ts": typescript

# Structured files (JSON/XML parsers)
structured_extensions:
  - ".json"
  - ".xml"
  - ".csproj"

# Documents (MarkItDown + header-based splitter)
document_extensions:
  - ".md"
  - ".pdf"
  - ".docx"

# Never indexed (binary, compiled artifacts)
exclude_extensions:
  - ".bin"
  - ".exe"
  - ".dll"

# Directories always skipped during discovery
exclude_dirs:
  - node_modules
  - .git
  - bin
  - obj
```

### Storage

```yaml
# ChromaDB persistence directory (relative to working directory).
# Override at runtime with the CHROMA_PERSIST_DIR environment variable.
chroma_persist_dir: "data/chroma_db"
```

### Embedding Model

```yaml
# HuggingFace model identifier. Must be the SAME for indexing and querying —
# changing this invalidates the existing database (clear and re-index).
embedding_model_name: "sentence-transformers/all-MiniLM-L6-v2"

# Local model cache directory. Downloaded once on first run; fully offline thereafter.
embedding_cache_dir: "data/models"

# Sliding window overlap between consecutive chunks (as a fraction of chunk size).
# Higher values improve context continuity at the cost of more chunks.
chunk_overlap_ratio: 0.2
```

### SCIP Indexers

```yaml
# Maps language names to their SCIP indexer CLI commands.
# Used by abyss-scip-prepare.ps1 and the ScipEnricher.
scip_indexers:
  dotnet: scip-dotnet
  python: scip-python
  java: scip-java
  typescript: scip-typescript
```

### Logging

All levels accept standard Python level names: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.  
Log output is written to both **stderr** and `logs/abyss.log` (10MB rotating, 5 backups).

```yaml
abyss_log_level: "INFO"         # Root logger — controls all Abyss output
chromadb_log_level: "WARNING"   # Reduce ChromaDB verbosity during indexing
httpx_log_level: "WARNING"      # Reduce HTTP client noise
llama_index_log_level: "WARNING" # Reduce LlamaIndex node parser spam
```

---

## Optional: SCIP Source Code Enrichment

SCIP (Source Code Intelligence Protocol) is a language-agnostic indexing protocol that captures **caller/callee relationships**, symbol kinds, and documentation. When a SCIP index is present, Abyss automatically enriches each code chunk with:

- `symbol` — full qualified symbol identifier
- `display_name` — human-readable name
- `kind` — `method`, `class`, `property`, `field`, `interface`, …
- `enclosing` — parent symbol (class / namespace)
- `documentation` — extracted doc comments
- `callers` — symbols that call this one (up to 10)
- `callees` — symbols called by this one (up to 10)

This dramatically improves search relevance for questions like *"who calls `ProcessPayment()`?"* or *"what does `OrderService` depend on?"*.

### Generating a SCIP Index

Use the included `abyss-scip-prepare.ps1` script:

```powershell
# Index a .NET solution
.\abyss-scip-prepare.ps1 -Path "D:\repos\MyApp" -Type dotnet

# Index a Python project
.\abyss-scip-prepare.ps1 -Path "D:\repos\MyApp" -Type python

# Index a TypeScript project
.\abyss-scip-prepare.ps1 -Path "D:\repos\MyApp" -Type typescript

# Index a Java project
.\abyss-scip-prepare.ps1 -Path "D:\repos\MyApp" -Type java
```

The script installs the required indexer if absent, runs it, and saves the output as `abyss.<type>.index.scip` in the target directory. Abyss automatically discovers `.scip` files when indexing.

| Language | Indexer | Runtime required |
|----------|---------|-----------------|
| .NET / C# | `scip-dotnet` | .NET SDK |
| Python | `@sourcegraph/scip-python` | Node.js / npm |
| TypeScript / JS | `@sourcegraph/scip-typescript` | Node.js / npm |
| Java | `scip-java` (via Coursier) | JDK |

> SCIP enrichment is **optional**. Without it, code chunks are still indexed and searchable — they simply lack caller/callee metadata and symbol documentation.

---

## Debugging the Embedding Process

Abyss can export one **self-contained HTML debug report per source file**, providing a complete view of how each file was chunked, what metadata was extracted, and what text was ultimately embedded.

### Enabling Debug Mode

```yaml
# config.yaml
embed_builder_debug: true
embed_builder_debug_output_dir: "logs/EmbedBuilder"
```

After indexing, one `.html` file per source file appears in `logs/EmbedBuilder/`. For example, `OrderService.cs` produces `OrderService.cs.html`.

### Reading the Debug Report

Each report is a scrollable table — one row per chunk — with color-coded columns:

| Color | Category | Keys |
|-------|----------|------|
| 🔵 Blue | File-level metadata | `file_path`, `file_name`, `language`, `doc_type`, `chunk_type`, `parser_fallback`, `markitdown_converted`, `original_doc_type` |
| 🟢 Green | **Chunk-level metadata** — Positional | `start_line`, `end_line`, `is_partial` |
| 🟢 Green | **Markdown sections** (markdown files) | `section_title`, `section_level`, `section_hierarchy`, `header_levels`, `has_code_blocks`, `code_block_count`, `word_count` |
| 🟢 Green | **Markdown rich content** (markdown files) | `has_checkboxes`, `checkbox_count`, `checked_count`, `unchecked_count`, `has_links`, `link_count`, `has_images`, `image_count`, `has_tables`, `table_count` |
| 🟢 Green | **JSON structured metadata** (`.json` files) | `json_path`, `json_key`, `json_keys`, `json_type`, `is_array`, `is_object` |
| 🟢 Green | **XML structured metadata** (`.xml`, `.csproj`, etc.) | `xml_path`, `xml_tag`, `xml_root`, `tag_count`, `child_count`, `is_grouped` |
| 🟠 Orange | SCIP-enriched metadata (code chunks) | `symbol`, `display_name`, `kind`, `enclosing`, `documentation`, `callers`, `callees` |
| — | Embedded text | The full semantically-enriched text sent to the embedding model |

The debug reports have no external dependencies and can be opened directly in any browser. They are ideal for diagnosing chunking quality, verifying metadata extraction, and understanding why certain queries do or do not match expected results.

---

## License

This project is licensed under the GPLv3 License — see the [LICENSE](LICENSE) file for details.
