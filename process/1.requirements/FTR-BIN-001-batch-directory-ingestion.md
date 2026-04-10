# FTR-BIN-001: Batch Directory Ingestion

## Overview
Replace the monolithic `index_directory` ingestion strategy with a batched pipeline that
processes files in configurable-size groups. For very large directories (above a configurable
threshold), the tool returns a pre-check response and requires an explicit confirmation flag
before proceeding — consistent with the existing `clear_database` two-call pattern.

## Stakeholders
- **Owner**: Abyss dev team
- **Consumers**: MCP clients (AI agents such as Copilot, IDE plugins, CLI callers)

---

## Functional Requirements

### RQ-BIN-001: File-Batch Processing
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The `index_directory` tool SHALL process matching files in sequential batches
  of at most `INGEST_BATCH_SIZE` files, accumulating results across all batches before
  returning a single response.
- **Rationale**: Processing all files in one operation exhausts the server's working memory for
  large codebases (observed 400 error on XplorerEditor with thousands of C# files).
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory containing 250 files matching the requested extensions
  And INGEST_BATCH_SIZE is 100
  When index_directory is called
  Then the pipeline processes 3 batches (100 + 100 + 50)
  And all 250 files are indexed in the database
  And the response contains per-batch statistics
  ```
- **Dependencies**: RQ-BIN-004 (batch configuration)

---

### RQ-BIN-002: Large Directory Pre-Check
- **Category**: Functional
- **EARS Type**: Event-driven
- **Statement**: WHEN the number of matching files in the target directory exceeds
  `INGEST_LARGE_DIR_THRESHOLD`, the `index_directory` tool SHALL return a pre-check
  response without ingesting any files, including the file count and a
  `requires_confirmation` flag set to `true`.
- **Rationale**: Prevents accidental multi-hour indexations and gives the caller visibility
  into the size of the operation before committing.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory containing 12,000 matching files
  And INGEST_LARGE_DIR_THRESHOLD is 10,000
  When index_directory is called without confirm_large: true
  Then the tool returns status "requires_confirmation"
  And the response contains "file_count": 12000
  And no files are ingested into the database
  ```
- **Dependencies**: RQ-BIN-003, RQ-BIN-004

---

### RQ-BIN-003: Two-Call Confirmation Protocol
- **Category**: Functional
- **EARS Type**: Event-driven
- **Statement**: WHEN `index_directory` is called with `confirm_large: true` and the
  matching file count exceeds `INGEST_LARGE_DIR_THRESHOLD`, the tool SHALL proceed with
  batched ingestion as defined in RQ-BIN-001.
- **Rationale**: Mirrors the existing `clear_database` confirm pattern, which is already
  understood by MCP clients. Keeps the API consistent.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory containing 12,000 matching files
  And INGEST_LARGE_DIR_THRESHOLD is 10,000
  When index_directory is called with confirm_large: true
  Then batched ingestion proceeds for all 12,000 files
  And the response contains full batch statistics
  ```
- **Dependencies**: RQ-BIN-002

---

### RQ-BIN-004: Batch Configuration via config.yaml
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The `index_directory` tool SHALL read `INGEST_BATCH_SIZE` and
  `INGEST_LARGE_DIR_THRESHOLD` from config.py (with YAML override support), defaulting
  to 100 and 10,000 respectively.
- **Rationale**: Operators need to tune batch size for their hardware (RAM, GPU, Ollama
  throughput) without modifying source code.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given config.yaml contains ingest_batch_size: 50
  When the MCP server starts
  Then INGEST_BATCH_SIZE equals 50
  And INGEST_LARGE_DIR_THRESHOLD equals 10000 (default)
  ```
- **Dependencies**: None

---

### RQ-BIN-005: Per-Batch Progress in Response
- **Category**: Functional
- **EARS Type**: Ubiquitous
- **Statement**: The `index_directory` tool response SHALL include a `batches` array
  where each element reports the batch index, file count processed, chunks created, and
  any error message for that batch.
- **Rationale**: Gives the caller (and the user) visibility into how many files were
  successfully processed and where any failure occurred.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory of 250 files processed in 3 batches
  When index_directory completes
  Then the response contains a "batches" array with 3 elements
  And each element contains "batch_index", "files_processed", "chunks_created"
  And the response contains totals "total_files" and "total_chunks"
  ```
- **Dependencies**: RQ-BIN-001

---

### RQ-BIN-006: Stop-on-Batch-Failure
- **Category**: Functional
- **EARS Type**: Unwanted-behavior
- **Statement**: IF a batch raises an unhandled exception during ingestion, THEN the
  `index_directory` tool SHALL stop processing immediately, set the response status to
  `"partial"`, and report the number of successfully completed batches and total files
  indexed before the failure.
- **Rationale**: Partial indexation is preferable to silent data loss; the caller can
  decide whether to retry or clear and restart.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory of 250 files in 3 batches
  And batch 2 raises an exception
  When index_directory is called
  Then batch 1 results are committed to the database
  And batch 2 and 3 are NOT processed
  And the response status is "partial"
  And the response reports "batches_completed": 1 and "batches_failed": 1
  ```
- **Dependencies**: RQ-BIN-001, RQ-BIN-005

---

## Non-Functional Requirements

### RQ-BIN-007: No Regression on Small Directories
- **Category**: Non-Functional
- **NFR Type**: Reliability
- **EARS Type**: Ubiquitous
- **Statement**: The `index_directory` tool SHALL produce identical indexed output for
  directories with fewer files than `INGEST_BATCH_SIZE` as it did before the batch
  ingestion change.
- **Metric**: All existing unit tests for `IngestionPipeline.ingest_directory` pass
  without modification.
- **Measurement Method**: Run full pytest suite; zero regressions.
- **Priority**: Must
- **Acceptance Criteria**:
  ```gherkin
  Given a directory with 5 files
  And INGEST_BATCH_SIZE is 100
  When index_directory is called
  Then all 5 files are indexed in a single batch
  And behavior is identical to the pre-batch implementation
  ```
- **Dependencies**: RQ-BIN-001
