# PLAN-BIN-001: Batch Directory Ingestion

## Overview
Implements batched file ingestion and the large-directory confirmation gate in the Abyss
MCP server, eliminating the 400 context-length error observed on large codebases.

## References
- **Requirements**: RQ-BIN-001, RQ-BIN-002, RQ-BIN-003, RQ-BIN-004, RQ-BIN-005, RQ-BIN-006, RQ-BIN-007
- **ADRs**: ADR-BIN-001 (DEC-BIN-001, DEC-BIN-002, DEC-BIN-003, DEC-BIN-004)

---

## Tasks

### TASK-BIN-001: Add batch config constants to config.py
- **Tier**: S
- **Status**: Not Started
- **Description**: Add `INGEST_BATCH_SIZE` and `INGEST_LARGE_DIR_THRESHOLD` constants to
  `config.py` following the existing `_DEFAULT_*` + `_get_config_value()` pattern.
  Add both keys to `_CONFIG_KEYS`.
- **Requirement refs**: RQ-BIN-004
- **ADR refs**: DEC-BIN-004
- **Acceptance Criteria**:
  ```gherkin
  Given config.py is loaded with no config.yaml overrides
  When INGEST_BATCH_SIZE is read
  Then it equals 100
  And INGEST_LARGE_DIR_THRESHOLD equals 10000
  ```
- **Dependencies**: None
- **Assignee**: AI

---

### TASK-BIN-002: Document new constants in config.yaml
- **Tier**: S
- **Status**: Not Started
- **Description**: Add `ingest_batch_size` and `ingest_large_dir_threshold` YAML entries
  with comments explaining their role, below the chunk parameters section.
- **Requirement refs**: RQ-BIN-004
- **ADR refs**: DEC-BIN-004
- **Acceptance Criteria**:
  ```gherkin
  Given config.yaml is loaded
  When ingest_batch_size key is present
  Then config.py reads it and overrides the default
  ```
- **Dependencies**: TASK-BIN-001
- **Assignee**: AI

---

### TASK-BIN-003: Refactor IngestionPipeline.ingest_directory() to batch processing
- **Tier**: M
- **Status**: Not Started
- **Description**: Refactor `ingest_directory()` in `ingestion_pipeline.py` to process files
  in sequential batches of `INGEST_BATCH_SIZE`. Return a `batches` list in the response.
  On batch failure, stop immediately and return status `"partial"` with `batches_completed`
  and `batches_failed` counters (DEC-BIN-003). Remove the hardcoded `BATCH_SIZE = 50`
  magic literal from `_embed_and_store` and replace it with a named constant.
- **Requirement refs**: RQ-BIN-001, RQ-BIN-005, RQ-BIN-006, RQ-BIN-007
- **ADR refs**: DEC-BIN-001, DEC-BIN-003
- **Acceptance Criteria**:
  ```gherkin
  Given a directory with 5 files and INGEST_BATCH_SIZE=100
  When ingest_directory is called
  Then all 5 files are processed in a single batch
  And the response contains "batches" with 1 element
  And status is "ok"

  Given a directory with 250 files and INGEST_BATCH_SIZE=100
  When ingest_directory is called
  Then files are processed in 3 batches (100+100+50)
  And the response contains "batches" with 3 elements

  Given batch 2 of 3 raises an exception
  When ingest_directory is called
  Then status is "partial"
  And batches_completed is 1, batches_failed is 1
  ```
- **Dependencies**: TASK-BIN-001
- **Assignee**: AI

---

### TASK-BIN-004: Add large-directory gate to index_directory tool in server.py
- **Tier**: M
- **Status**: Not Started
- **Description**: Before calling `pipeline.ingest_directory()`, count matching files. If
  count exceeds `INGEST_LARGE_DIR_THRESHOLD` and `confirm_large` is not `true`, return
  `status: "requires_confirmation"`. Add `confirm_large` boolean to the tool's `inputSchema`.
  Import `INGEST_LARGE_DIR_THRESHOLD` from config. Use a dedicated `_count_matching_files()`
  helper function (fast walk, no parsing).
- **Requirement refs**: RQ-BIN-002, RQ-BIN-003
- **ADR refs**: DEC-BIN-002
- **Acceptance Criteria**:
  ```gherkin
  Given a directory with 12000 files and INGEST_LARGE_DIR_THRESHOLD=10000
  When index_directory is called without confirm_large
  Then status is "requires_confirmation" and no files are ingested

  When index_directory is called with confirm_large: true
  Then batched ingestion proceeds
  ```
- **Dependencies**: TASK-BIN-001, TASK-BIN-003
- **Assignee**: AI

---

### TASK-BIN-005: Unit tests for batch ingestion
- **Tier**: M
- **Status**: Not Started
- **Description**: Add unit tests covering: single-batch (small dir), multi-batch (large dir),
  stop-on-failure, config defaults, and large-dir gate (requires_confirmation).
- **Requirement refs**: RQ-BIN-001, RQ-BIN-002, RQ-BIN-003, RQ-BIN-006, RQ-BIN-007
- **ADR refs**: ADR-BIN-001
- **Acceptance Criteria**:
  ```gherkin
  Given unit tests are run with pytest
  When all BIN tests execute
  Then all pass with zero failures and zero modifications to test expectations
  ```
- **Dependencies**: TASK-BIN-003, TASK-BIN-004
- **Assignee**: AI
