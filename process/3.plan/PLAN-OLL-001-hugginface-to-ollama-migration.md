# PLAN-OLL-001: HuggingFace to Ollama Migration

## Overview
Implements the migration from HuggingFaceEmbedding to OllamaEmbedding across the Abyss codebase.
Covers dependency update, configuration changes, EmbeddingService refactor, and
IngestionPipeline chunk-params cleanup.

## References
- **Requirements**: RQ-OLL-001, RQ-OLL-002, RQ-OLL-003, RQ-OLL-004, RQ-OLL-005, RQ-OLL-006, RQ-OLL-007
- **ADRs**: ADR-OLL-001 (DEC-OLL-001, DEC-OLL-002, DEC-OLL-003, DEC-OLL-004)

---

## Tasks

### TASK-OLL-001: Update Python dependencies
- **Tier**: S
- **Status**: Done
- **Description**: Remove `llama-index-embeddings-huggingface` and add
  `llama-index-embeddings-ollama` in `requirements.txt`.
- **Requirement refs**: RQ-OLL-001, RQ-OLL-005
- **ADR refs**: DEC-OLL-001
- **Acceptance Criteria**:
  - Given the updated requirements.txt
  - When `pip install -r requirements.txt` runs
  - Then `llama_index.embeddings.ollama` is importable and
    `llama_index.embeddings.huggingface` is not installed
- **Dependencies**: None
- **Assignee**: AI

---

### TASK-OLL-002: Add Ollama config params and remove HuggingFace params
- **Tier**: M
- **Status**: Done
- **Description**: Update `config.py` and `config.yaml` to replace
  `embedding_model_name` / `embedding_cache_dir` with `ollama_base_url` /
  `ollama_embedding_model`, and to add explicit `chunk_size` constant replacing
  the dynamic inference.  Retain `chunk_overlap_ratio`.
- **Requirement refs**: RQ-OLL-002, RQ-OLL-003, RQ-OLL-004
- **ADR refs**: DEC-OLL-002, DEC-OLL-003
- **Acceptance Criteria**:
  - Given no config.yaml overrides
  - When config.py loads
  - Then OLLAMA_BASE_URL == "http://localhost:11434",
    OLLAMA_EMBEDDING_MODEL == "nomic-embed-text",
    CHUNK_SIZE is a positive integer constant
  - And EMBEDDING_MODEL_NAME and EMBEDDING_CACHE_DIR no longer exist
- **Dependencies**: None
- **Assignee**: AI

---

### TASK-OLL-003: Refactor EmbeddingService to use OllamaEmbedding
- **Tier**: M
- **Status**: Done
- **Description**: Rewrite `embedding_service.py` to wrap `OllamaEmbedding` instead of
  `HuggingFaceEmbedding`. Remove `_ensure_snapshot`, `get_max_seq_length`,
  `_snapshot_path`, and all HuggingFace / huggingface_hub imports. Preserve the
  singleton pattern and `get_embed_model()` public API.
- **Requirement refs**: RQ-OLL-001, RQ-OLL-005, RQ-OLL-007
- **ADR refs**: DEC-OLL-001, DEC-OLL-004
- **Acceptance Criteria**:
  - Given OllamaEmbedding is configured with OLLAMA_BASE_URL and OLLAMA_EMBEDDING_MODEL
  - When get_embed_model() is called
  - Then an OllamaEmbedding instance is returned from the singleton
  - And no huggingface or snapshot_download call is made
- **Dependencies**: TASK-OLL-001, TASK-OLL-002
- **Assignee**: AI

---

### TASK-OLL-004: Replace _infer_chunk_params with config constants in IngestionPipeline
- **Tier**: M
- **Status**: Done
- **Description**: Remove the `_infer_chunk_params()` function from
  `ingestion_pipeline.py` and replace the `_chunk_params` cached_property with
  a direct read from `CHUNK_SIZE` and `CHUNK_OVERLAP` config constants.
  Update imports accordingly.
- **Requirement refs**: RQ-OLL-004, RQ-OLL-005
- **ADR refs**: DEC-OLL-003
- **Acceptance Criteria**:
  - Given CHUNK_SIZE=512 and CHUNK_OVERLAP_RATIO=0.2 in config
  - When IngestionPipeline._chunk_params is accessed
  - Then it returns (512, 102)
  - And _infer_chunk_params is not called
- **Dependencies**: TASK-OLL-002
- **Assignee**: AI

---

### TASK-OLL-005: Install updated dependencies
- **Tier**: S
- **Status**: Done
- **Description**: Run `pip install -r requirements.txt` in the virtual environment
  to install `llama-index-embeddings-ollama` and remove the superseded packages.
- **Requirement refs**: RQ-OLL-001
- **ADR refs**: DEC-OLL-001
- **Acceptance Criteria**:
  - Given the updated requirements.txt
  - When the command completes
  - Then `python -c "from llama_index.embeddings.ollama import OllamaEmbedding"` exits 0
- **Dependencies**: TASK-OLL-001
- **Assignee**: AI
