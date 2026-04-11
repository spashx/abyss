# FTR-OLL-001: Migration from HuggingFaceEmbedding to Ollama

## Overview
Abyss currently loads embedding models in-process via `HuggingFaceEmbedding` (llama_index) and
`snapshot_download` (huggingface_hub). This causes slow cold startup: the model must be downloaded
or loaded from disk on every MCP server start. The goal of this feature is to delegate embedding
generation to a locally running Ollama server, eliminating in-process model loading entirely and
reducing startup time to near-zero for the embedding subsystem.

## Stakeholders
- **Owner**: Abyss maintainer
- **Consumers**: IngestionPipeline, QueryEngine, EmbeddingService, config.py, config.yaml

---

## Functional Requirements

### RQ-OLL-001: Ollama as Embedding Provider
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The Abyss application SHALL use an Ollama server as the embedding provider,
  replacing the HuggingFaceEmbedding in-process model.
- **Rationale**: Eliminates in-process model loading and huggingface_hub dependency, dramatically
  reducing cold startup time.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given the Abyss MCP server starts
  - When a directory is indexed or a query is made
  - Then embeddings are obtained via HTTP calls to the Ollama server and no
    HuggingFaceEmbedding or snapshot_download call is made
- **Dependencies**: None

---

### RQ-OLL-002: Ollama Base URL Configuration
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The Abyss application SHALL expose the Ollama server base URL as a named
  configuration parameter (`ollama_base_url`) in config.py and config.yaml, with a sensible
  default (`http://localhost:11434`).
- **Rationale**: Users may run Ollama on a non-default host or port; the URL must not be
  hard-coded.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given config.yaml does not define `ollama_base_url`
  - When the application loads
  - Then `OLLAMA_BASE_URL` equals `http://localhost:11434`
  - And given config.yaml defines `ollama_base_url: http://myhost:11434`
  - When the application loads
  - Then `OLLAMA_BASE_URL` equals `http://myhost:11434`
- **Dependencies**: None

---

### RQ-OLL-003: Ollama Model Name Configuration
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The Abyss application SHALL expose the Ollama embedding model name as a named
  configuration parameter (`ollama_embedding_model`) in config.py and config.yaml, replacing the
  former `embedding_model_name` HuggingFace parameter.
- **Rationale**: Different Ollama model families produce vectors of different dimensionality;
  the model must be explicit and user-selectable.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given config.yaml does not define `ollama_embedding_model`
  - When the application loads
  - Then `OLLAMA_EMBEDDING_MODEL` equals the built-in default (e.g. `nomic-embed-text`)
  - And given config.yaml defines `ollama_embedding_model: mxbai-embed-large`
  - When the application loads
  - Then `OLLAMA_EMBEDDING_MODEL` equals `mxbai-embed-large`
- **Dependencies**: RQ-OLL-001

---

### RQ-OLL-004: Explicit Chunk Size Configuration
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The Abyss application SHALL expose `chunk_size` and `chunk_overlap` as explicit
  named configuration parameters in config.py and config.yaml, replacing the dynamic
  `_infer_chunk_params()` function that previously derived them from the HuggingFace model's
  `max_seq_length` property.
- **Rationale**: Ollama does not expose model properties such as `max_seq_length`; chunk
  parameters must therefore be declared statically and kept consistent with the chosen model.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given the Abyss application starts with no config.yaml overrides
  - When IngestionPipeline initializes chunk parameters
  - Then `CHUNK_SIZE` equals the built-in default constant and `CHUNK_OVERLAP` equals
    `round(CHUNK_SIZE * CHUNK_OVERLAP_RATIO)`
  - And given config.yaml defines `chunk_size: 2000`
  - When IngestionPipeline initializes
  - Then `CHUNK_SIZE` equals 2000
- **Dependencies**: RQ-OLL-001

---

### RQ-OLL-005: Removal of HuggingFace-Specific Code
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The Abyss application SHALL remove all HuggingFace-specific code, including
  `snapshot_download`, `EMBEDDING_CACHE_DIR`, the `_ensure_snapshot` method, `_infer_chunk_params`
  model-introspection logic, and all `huggingface_hub` / `llama_index.embeddings.huggingface`
  imports.
- **Rationale**: Dead code increases maintenance burden and keeps unnecessary packages in the
  dependency set.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given the migrated codebase
  - When a grep is run for `huggingface`, `snapshot_download`, `EMBEDDING_CACHE_DIR`,
    `_ensure_snapshot`
  - Then no matches are found in any source file
- **Dependencies**: RQ-OLL-001, RQ-OLL-004

---

## Non-Functional Requirements

### RQ-OLL-006: Startup Time Reduction
- **Category**: Non-Functional
- **NFR Type**: Performance
- **EARS Type**: Ubiquitous
- **Statement**: WHILE the Ollama server is already running with the embedding model loaded, the
  Abyss MCP server SHALL complete initialization without performing any in-process model load,
  resulting in a cold startup time that does not include model download or in-process model
  initialization overhead.
- **Metric**: No in-process model load on startup (verified by absence of `snapshot_download`
  call and no HuggingFaceEmbedding instantiation).
- **Measurement Method**: Code review and absence of `huggingface_hub` import in final codebase.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given the Ollama server is running
  - When the Abyss MCP server starts
  - Then server logs show no model download or local-model-load messages
- **Dependencies**: RQ-OLL-001, RQ-OLL-005

---

### RQ-OLL-007: Graceful Error on Ollama Unavailability
- **Category**: Non-Functional
- **NFR Type**: Reliability
- **EARS Type**: Unwanted-behavior
- **Statement**: IF the Ollama server is unavailable when an embedding is requested, THEN the
  Abyss application SHALL propagate the error with a clear log message identifying the configured
  Ollama URL and model, and SHALL NOT silently return empty or zero vectors.
- **Metric**: Exception propagated with log entry containing `OLLAMA_BASE_URL` and
  `OLLAMA_EMBEDDING_MODEL` values.
- **Measurement Method**: Unit test simulating Ollama HTTP failure.
- **Priority**: Must
- **Acceptance Criteria**:
  - Given the Ollama server is not reachable at the configured URL
  - When an embedding is requested
  - Then an exception is raised
  - And the log contains the configured URL and model name
- **Dependencies**: RQ-OLL-001, RQ-OLL-002
