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

Abyss is a local **Retrieval-Augmented Generation (RAG)** server that indexes your source code and documentation, then exposes semantic search through the **Model Context Protocol (MCP)**.

---

## Key Features

- **100% offline** -- no cloud API, no telemetry, no data leaves your machine
- **No GPU required** -- embeddings are delegated to a local Ollama server (CPU-friendly models available)
- **MCP-native** -- integrates into VS Code, Claude Desktop, and any MCP-compatible client
- **Semantic search** -- vector similarity search over code and documentation
- **Multi-language code parsing** -- syntax-aware AST chunking via Tree-sitter (C#, Python, Java, TypeScript, JavaScript, HTML)
- **Document ingestion** -- PDF, DOCX, PPTX, XLSX, EPUB, images (OCR), Markdown, plain text
- **Structured file parsing** -- JSON (per-key/array groups) and XML (per-element groups)
- **SCIP enrichment** -- optional caller/callee graph indexing for deep code navigation
- **Advanced filtering** -- filter results by language, kind, file path, line range, text
- **Persistent storage** -- ChromaDB SQLite database, survives restarts
- **Debug mode** -- per-file HTML reports showing chunks, metadata, and semantic headers

---

## Setup

### Prerequisites

- **Python 3.13**
- **[uv](https://github.com/astral-sh/uv)** -- fast Python package manager
- **[Ollama](https://ollama.com/)** -- local model server (must be running before starting Abyss)

Install `uv` if needed:

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install

```bash
git clone https://github.com/<your-org>/abyss.git
cd abyss
```

**Windows (PowerShell):**

```powershell
.\install-deps-for-dev.ps1
```

**macOS / Linux:**

```bash
uv venv .venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt
```

The setup script creates a `.venv/`, installs dependencies, and prints the MCP configuration block.

Before starting Abyss, pull the embedding model into Ollama:

```bash
ollama pull all-minilm:l6-v2
```

Ollama must be running when Abyss starts. All embedding calls are made locally over HTTP -- no data leaves your machine.

### Connect to VS Code

Create `.vscode/mcp.json` in your workspace. Replace `<local_repos_path>` with the absolute path to this repository.

**Windows:**

```json
{
  "servers": {
    "abyss": {
      "command": "<local_repos_path>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "abyss"],
      "env": { "PYTHONPATH": "<local_repos_path>\\src" }
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
      "args": ["-m", "abyss"],
      "env": { "PYTHONPATH": "<local_repos_path>/src" }
    }
  }
}
```

Verify by checking the `rag://status` resource -- it should report `"status": "ok"`.

---

## Usage

### MCP Tools

| Tool | Description |
|------|-------------|
| `index_directory` | Recursively index a directory. Accepts `include_extensions` and `exclude_extensions`. |
| `query` | Semantic search with filters (language, kind, file path, line range, text). |
| `list_documents` | List indexed files with metadata (name, date, size, chunk count). |
| `list_sources` | List unique metadata values (file paths, languages, kinds, chunk types) for filtering. |
| `list_filterable_fields` | Describe all filterable metadata fields with types, operators, and examples. |
| `replace_document` | Re-index a single file after modification. |
| `remove_document` | Remove a file and its chunks from the database (source file untouched). |
| `clear_database` | Erase all chunks and registry. Requires `confirm: true`. |

### MCP Resources

| URI | Description |
|-----|-------------|
| `rag://status` | Server health, document/chunk counts, last indexation summary |
| `rag://supported-extensions` | Indexed file types grouped by parser |
| `rag://stats` | Content breakdown by language, kind, and chunk type |

### Query Examples

**Find C# methods related to "validate":**
```json
{
  "question": "validate input",
  "top_k": 10,
  "filters": { "languages": ["csharp"], "kinds": ["method"] }
}
```

**Search only documentation:**
```json
{
  "question": "how to install dependencies",
  "top_k": 5,
  "filters": { "chunk_types": ["document"] }
}
```

**Search within a specific file and line range:**
```json
{
  "question": "authentication token validation",
  "top_k": 6,
  "filters": { "sources": ["src/Auth/AuthService.cs"], "line_min": 50, "line_max": 200 }
}
```

### Available Query Filters

| Filter | Type | Description |
|--------|------|-------------|
| `sources` | `string[]` | Exact file paths |
| `languages` | `string[]` | e.g. `["csharp", "python"]` |
| `kinds` | `string[]` | SCIP symbol kind: `"method"`, `"class"`, `"property"`, `"field"` |
| `chunk_types` | `string[]` | `"code"`, `"document"`, `"structured"` |
| `file_path_contains` | `string` | Substring match on file path |
| `line_min` / `line_max` | `integer` | Restrict to a line range |
| `must_contain` | `string` | Full-text substring that must be present in the chunk |

### Preparing a Directory for Ingestion

Abyss skips common noise directories by default (`node_modules`, `.git`, `bin`, `obj`, `dist`, `build`, `.venv`, etc.) and excludes binary extensions (`.bin`, `.exe`, `.dll`, `.obj`, `.pdb`).

Add project-specific exclusions in `config.yaml` or pass inline filters:

```json
{
  "path": "D:/repos/MyProject",
  "include_extensions": [".cs", ".md"],
  "exclude_extensions": [".g.cs", ".designer.cs"]
}
```

| Scenario | Recommendation |
|----------|---------------|
| Large monorepos | Index sub-projects separately with targeted `include_extensions` |
| JavaScript/TypeScript | Exclude `node_modules`, `dist`, `.min.js`, `.map` |
| .NET projects | Exclude `bin`, `obj`, `.g.cs`, `.designer.cs` |
| Python projects | Exclude `__pycache__`, `.venv` |
| Documentation only | Use `include_extensions: [".md", ".rst", ".txt"]` |

### SCIP Enrichment (Optional)

SCIP adds caller/callee relationships, symbol kinds, and documentation to code chunks. Generate an index with:

```powershell
.\abyss-scip-prepare.ps1 -Path "D:\repos\MyApp" -Type dotnet    # or: python, typescript, java
```

The script installs the required indexer, runs it, and saves the output as `abyss.<type>.index.scip`. Abyss discovers `.scip` files automatically during indexing.

| Language | Indexer | Runtime required |
|----------|---------|-----------------|
| .NET / C# | `scip-dotnet` | .NET SDK |
| Python | `@sourcegraph/scip-python` | Node.js / npm |
| TypeScript / JS | `@sourcegraph/scip-typescript` | Node.js / npm |
| Java | `scip-java` (via Coursier) | JDK |

Without SCIP, code chunks are still indexed and searchable -- they just lack caller/callee metadata.

---

## Configuration

All settings live in `config.yaml` at the repository root. Missing keys fall back to built-in defaults.

### File Extensions

```yaml
# Source code: extension -> Tree-sitter language name
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

# Never indexed
exclude_extensions:
  - ".bin"
  - ".exe"
  - ".dll"

# Directories always skipped
exclude_dirs:
  - node_modules
  - .git
  - bin
  - obj
```

### Storage

```yaml
chroma_persist_dir: "data/chroma_db"
```

### Ollama Embedding

```yaml
# URL of the local Ollama server
ollama_base_url: "http://localhost:11434"

# Model used for both indexing and querying -- must be the same for both
ollama_embedding_model: "all-minilm:l6-v2"

# Characters per chunk -- keep consistent with the model context window
chunk_size: 256

# Overlap as a fraction of chunk_size
chunk_overlap_ratio: 0.2
```

> The same model **must** be used for indexing and querying -- mixing models corrupts the vector space. Run `ollama pull <model>` before switching, then clear and re-index.

### SCIP Indexers

```yaml
scip_indexers:
  dotnet: scip-dotnet
  python: scip-python
  java: scip-java
  typescript: scip-typescript
```

### Logging

Log output goes to both **stderr** and `logs/abyss.log` (10MB rotating, 5 backups).

```yaml
abyss_log_level: "INFO"
chromadb_log_level: "WARNING"
httpx_log_level: "WARNING"
llama_index_log_level: "WARNING"
```

### Debug Reports

```yaml
embed_builder_debug: true
embed_builder_debug_output_dir: "logs/EmbedBuilder"
```

Produces one self-contained HTML file per indexed source file, showing chunks, metadata, and the final embedded text. Open directly in any browser.

---


## Example of usage

see [Examples](https://github.com/spashx/abyss/tree/main/examples/) of what you can achieve with Abyss.


## Architecture

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Orchestration** | [LlamaIndex](https://www.llamaindex.ai/) |
| **Code parsing** | [Tree-sitter](https://tree-sitter.github.io/) + `tree-sitter-language-pack` |
| **SCIP indexing** | [SCIP protocol](https://scip-code.org/) (optional) |
| **Document conversion** | [MarkItDown](https://github.com/microsoft/markitdown) (Microsoft) |
| **Embeddings** | [Ollama](https://ollama.com/) (`all-minilm:l6-v2` default, configurable) |
| **Vector database** | [ChromaDB](https://www.trychroma.com/) (embedded SQLite) |
| **Runtime** | Python 3.13, managed with [uv](https://github.com/astral-sh/uv) |

### Ingestion Pipeline

Files are transformed into searchable vector chunks through five stages:

```
File Discovery  ->  Parsing  ->  SCIP Enrichment  ->  EmbedBuilder  ->  Embedding & Storage
```

1. **File Discovery** -- recursive glob, size filter (max 10MB), exclude dirs/extensions, classify by type
2. **Parsing** -- dispatched by file type:
   - Code -> Tree-sitter AST splitter (chunks at function/class boundaries)
   - JSON -> per-key/array group units, merged to chunk size
   - XML -> per-element units, merged to chunk size
   - Documents -> MarkItDown conversion, then header-based section splitting
   - Unknown -> sentence-level splitting fallback
3. **SCIP Enrichment** (optional) -- matches chunks to SCIP index, injects symbol/caller/callee metadata
4. **EmbedBuilder** -- prepends a semantic header (file, language, symbol, kind, callers, callees) to each chunk
5. **Embedding & Storage** -- batch-encodes with the embedding model, upserts into ChromaDB

---

## License

This project is licensed under the GPLv3 License -- see the [LICENSE](LICENSE) file for details.
