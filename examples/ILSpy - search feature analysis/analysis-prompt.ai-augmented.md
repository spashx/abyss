# ILSpy Search Feature Analysis — AI-Augmented Prompt
**Version:** 1.0 | **Date:** 2026-03-12 | **Target Agent:** Agentic AI with MCP Abyss + file creation capabilities

---

## 0. CONTEXT & PREAMBLE

### 0.1 The Knowledge Base
The Abyss MCP server has **293 documents / 1,746 chunks** indexed from `D:\repos\github\ILSpy\ILSpy`.  
All factual claims about ILSpy code MUST be grounded in Abyss query results. Never hallucinate code.

### 0.2 Available MCP Tools (always prefer over assumptions)
| Tool | Purpose |
|---|---|
| `list_documents` | Enumerate all indexed files |
| `query` | Semantic + filtered vector search |
| `list_sources` | Show filter values for sources |
| `list_filterable_fields` | Describe metadata fields available for filtering |

### 0.3 Expert Persona
Act as a **senior C#/.NET software architect** with 10+ years of WPF application architecture experience. Every technical claim must be traceable to code evidence retrieved from the knowledge base.

---

## 1. EARS REQUIREMENTS

> EARS = Easy Approach to Requirements Syntax.  
> Format: `WHEN [trigger] THE SYSTEM SHALL [action]` / `THE SYSTEM SHALL [always-on behavior]` / `IF [unwanted condition] THEN THE SYSTEM SHALL [response]`

### REQ-01 — Knowledge Base Entity Discovery
**WHEN** performing any code analysis about ILSpy Search features,  
**THE SYSTEM SHALL** query the Abyss knowledge base using multiple targeted semantic queries before making any structural claim.

**Acceptance Criteria:**
- AC-01.1: At minimum 8 distinct Abyss `query` calls covering: Search UI, Search model, Search filtering, Search result, SearchPane, SearchPaneModel, SearchResultFactory, and search-related commands.
- AC-01.2: Each query result must be inspected for class names, method signatures, call relationships (callers/callees from SCIP metadata).
- AC-01.3: IF a query returns fewer than 3 relevant chunks, THEN the system SHALL reformulate the query with synonyms and retry once.

### REQ-02 — Entity Relationship Mapping
**WHEN** all relevant entities have been discovered,  
**THE SYSTEM SHALL** produce a complete entity inventory listing all classes, interfaces, enums, and delegates involved in the Search subsystem.

**Acceptance Criteria:**
- AC-02.1: Each entity entry SHALL include: fully-qualified name, file path, kind (class/interface/enum/delegate), and a one-sentence responsibility description.
- AC-02.2: Relationships SHALL be classified as: Inheritance, Composition, Dependency (method call), Event subscription, Interface implementation.
- AC-02.3: The inventory SHALL distinguish **primary** entities (directly in `Search/` folder) from **secondary** entities (referenced from outside `Search/`).

### REQ-03 — Workflow Identification (Dynamic Calls)
**WHEN** entity relationships are mapped,  
**THE SYSTEM SHALL** identify at least 3 distinct user-triggered workflows involving the Search subsystem.

**Accepted workflows to cover:**
1. User types a search term → results appear in pane
2. User changes search filter / scope → results refresh
3. User selects a search result → navigation event fires

**Acceptance Criteria:**
- AC-03.1: Each workflow SHALL list the ordered sequence of method calls with originating class and target class.
- AC-03.2: For each method call in the sequence, the system SHALL annotate CRUD impact: **C**reate / **R**ead / **U**pdate / **D**elete on which objects.
- AC-03.3: SCIP `callers` / `callees` metadata from Abyss chunks SHALL be used as primary evidence; source code reading is secondary.

### REQ-04 — Mermaid Class Diagram
**WHEN** entity inventory is complete,  
**THE SYSTEM SHALL** generate a syntactically valid Mermaid `classDiagram` for the Search subsystem.

**Acceptance Criteria:**
- AC-04.1: The diagram SHALL include all primary entities and tier-1 secondary entities (directly referenced).
- AC-04.2: All relationships SHALL be labeled with their classification (see REQ-02).
- AC-04.3: Key methods (search trigger, filter, result handling) SHALL appear inside their respective class boxes.
- AC-04.4: The diagram SHALL compile without errors in a Mermaid renderer.

### REQ-05 — Mermaid Sequence Diagrams
**WHEN** workflows are identified,  
**THE SYSTEM SHALL** generate one `sequenceDiagram` per workflow identified in REQ-03.

**Acceptance Criteria:**
- AC-05.1: Each diagram SHALL show participant names matching actual class names from the codebase.
- AC-05.2: Each diagram SHALL include activation bars (using `activate`/`deactivate` syntax).
- AC-05.3: Async calls (Tasks, async/await patterns) SHALL be annotated with `-->>` notation and a note.
- AC-05.4: Each sequence diagram SHALL compile without errors in a Mermaid renderer.

### REQ-06 — HTML Report Generation
**WHEN** all analysis artifacts are produced (entity inventory, class diagram, sequence diagrams, CRUD tables),  
**THE SYSTEM SHALL** generate a single self-contained HTML file at path `d:\repos\github\spashx\abyss\examples\IlSpy analysis\ilspy-search-analysis.html`.

**Acceptance Criteria:**
- AC-06.1: The HTML file SHALL be fully self-contained (no external CSS/JS URLs — inline everything or use CDN-safe inline scripts).
- AC-06.2: The file SHALL render Mermaid diagrams inline using the Mermaid.js CDN script tag.
- AC-06.3: The report SHALL contain the following sections in order:
  1. Executive Summary
  2. Entity Inventory Table
  3. Feature Analysis: Search UI Pane
  4. Feature Analysis: Search Model
  5. Feature Analysis: Search Result Factory & Filtering
  6. Workflow Diagrams (class + sequence per workflow)
  7. CRUD Reference Table
  8. Recommendations (Quality + Cybersecurity)
  9. Appendix: Evidence References (Abyss query excerpts)
- AC-06.4: The visual design SHALL use a dark-on-light professional color scheme (suggested: navy/slate header, white body, accent color for tables).
- AC-06.5: The report SHALL include a table of contents with anchor links.
- AC-06.6: Each Mermaid diagram block SHALL have a descriptive caption beneath it.

### REQ-07 — Recommendations Section
**THE SYSTEM SHALL** produce a minimum of 5 quality recommendations and 3 cybersecurity recommendations based on code evidence found in the knowledge base.

**Acceptance Criteria:**
- AC-07.1: Each recommendation SHALL include: ID, severity (High/Medium/Low), description, evidence (file + line if known), suggested remediation.
- AC-07.2: Quality recommendations SHALL cover at minimum: separation of concerns, testability, observable patterns, performance.
- AC-07.3: Cybersecurity recommendations SHALL reference OWASP categories where applicable (even if desktop app, principle applies).

---

## 2. IMPLEMENTATION PLAN (TASK BREAKDOWN)

The implementation MUST follow the phases below in strict order. Do NOT skip phases.  
Mark each task complete before proceeding to the next.

---

### PHASE 1 — KNOWLEDGE GATHERING

#### TASK 1.1 — Baseline Document Map
```
ACTION: Call list_documents
PURPOSE: Confirm database state and identify all Search-related file paths
EXPECTED: Identify files containing "Search" in path or name
ARTIFACT: Internal list "search_files[]"
```

#### TASK 1.2 — Primary Entity Queries
Execute the following queries sequentially (do not batch; inspect each result before the next):

| Query ID | Query String | Filter Suggestion |
|---|---|---|
| Q1 | `"SearchPane search pane UI model WPF"` | `file_name contains "Search"` |
| Q2 | `"SearchPaneModel search results binding observable"` | `file_name contains "Search"` |
| Q3 | `"SearchResultFactory factory result creation filtering"` | none |
| Q4 | `"search text input filtering assembly member type"` | none |
| Q5 | `"ISearchResult search result interface contract"` | none |
| Q6 | `"search scope assembly namespace filter"` | none |
| Q7 | `"RunSearchAsync search background task cancellation"` | none |
| Q8 | `"search highlight match result display decompiler"` | none |

**After each query:** Extract class names, method names, callers, callees, file paths.

#### TASK 1.3 — Secondary Entity Discovery
```
ACTION: For each referenced class discovered in TASK 1.2 that is NOT in the Search folder,
        run 1-2 targeted queries to understand its contract.
QUERIES TO RUN: dependent on TASK 1.2 results (e.g. AssemblyTreeModel, Language, ISymbol)
ARTIFACT: Internal list "secondary_entities[]"
```

#### TASK 1.4 — SCIP Call Graph Extraction
```
ACTION: For each primary entity method, extract "callers" and "callees" from ABYSS chunk metadata.
PURPOSE: Build a call graph without reading source files.
ARTIFACT: Internal map "call_graph{class.method -> [callers], [callees]}"
```

---

### PHASE 2 — ENTITY ANALYSIS

#### TASK 2.1 — Entity Classification
```
FOR EACH entity in search_files[] + secondary_entities[]:
  - Determine: namespace, kind (class/interface/enum/delegate)
  - Determine: primary responsibility (1 sentence)
  - Determine: lifecycle (instantiated once / per-search / per-result)
  - Classify relationship to other entities (see REQ-02)
ARTIFACT: "entity_inventory.json" (internal)
```

#### TASK 2.2 — Relationship Matrix
```
BUILD a relationship matrix:
  Rows: source entity
  Columns: target entity
  Cell: relationship type (Inherits / Composes / Calls / Subscribes / Implements)
ARTIFACT: "relationship_matrix" (internal, will feed Mermaid diagram)
```

---

### PHASE 3 — WORKFLOW MODELING

#### TASK 3.1 — Workflow: Search Term Entry
```
TRIGGER: User types in search box
TRACE through:
  1. SearchBox (Control) → event fired
  2. SearchPane.xaml.cs handler
  3. SearchPaneModel → background search initiation
  4. SearchResultFactory → result creation
  5. Results bound to UI list
FOR EACH STEP: annotate CRUD (what object is Created/Read/Updated/Deleted)
```

#### TASK 3.2 — Workflow: Filter/Scope Change
```
TRIGGER: User changes search filter dropdown or scope selector
TRACE through the filter application path
FOR EACH STEP: annotate CRUD
```

#### TASK 3.3 — Workflow: Result Selection & Navigation
```
TRIGGER: User clicks a search result
TRACE through navigation to the decompiler pane
FOR EACH STEP: annotate CRUD
```

#### TASK 3.4 — Workflow Validation
```
FOR EACH workflow: cross-check with ABYSS callers/callees metadata
IF a step cannot be confirmed by evidence: mark as [INFERRED] in the diagram
```

---

### PHASE 4 — DIAGRAM GENERATION

#### TASK 4.1 — Class Diagram (Mermaid)
```
GENERATE classDiagram with:
  - All primary entities (from search_files[])
  - Tier-1 secondary entities
  - Labeled relationships
  - Key method signatures inside class boxes
VALIDATE: ensure no duplicate class names, valid Mermaid syntax
```

#### TASK 4.2 — Sequence Diagram: Search Term Entry
```
GENERATE sequenceDiagram for TASK 3.1 workflow
INCLUDE: activation bars, async annotations, return values
```

#### TASK 4.3 — Sequence Diagram: Filter Change
```
GENERATE sequenceDiagram for TASK 3.2 workflow
```

#### TASK 4.4 — Sequence Diagram: Result Navigation
```
GENERATE sequenceDiagram for TASK 3.3 workflow
```

---

### PHASE 5 — REPORT GENERATION

#### TASK 5.1 — CRUD Table Compilation
```
COMPILE a single CRUD table:
  Rows: Data objects (e.g., SearchResults, SearchQuery, AssemblyList)
  Columns: Workflow 1 / Workflow 2 / Workflow 3
  Cells: C / R / U / D / - (none)
```

#### TASK 5.2 — Recommendations Drafting
```
DRAFT based on evidence:
  Quality (>=5): naming, SRP, async pattern, testability, performance
  Security (>=3): input validation, SSRF (if any URL handling), assembly loading safety
FORMAT: per REQ-07 (ID, severity, description, evidence, remediation)
```

#### TASK 5.3 — HTML Report Assembly
```
ASSEMBLE report as a single HTML file.
STRUCTURE: per REQ-06 section list (AC-06.3)
STYLE: inline CSS, professional dark navy header, readable body
MERMAID: use CDN script from https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js
         Initialize with: mermaid.initialize({ startOnLoad: true, theme: 'default' })
OUTPUT FILE: d:\repos\github\spashx\abyss\examples\IlSpy analysis\ilspy-search-analysis.html
```

#### TASK 5.4 — Evidence Appendix
```
FOR EACH key claim in the report:
  - Cite the Abyss query that produced the evidence
  - Include the relevant chunk text (truncated to 200 chars)
  - Include file_path and chunk metadata
PLACE IN: Appendix section of HTML report
```

---

### PHASE 6 — VALIDATION & QA

#### TASK 6.1 — Diagram Syntax Check
```
MENTALLY validate each Mermaid block:
  - No unclosed brackets
  - No duplicate participant names
  - Valid arrow types (-->>, ->>, ->>)
  - Class diagram: no syntax errors in method declarations
```

#### TASK 6.2 — Report Completeness Check
```
VERIFY all 9 sections from AC-06.3 are present
VERIFY TOC anchor links match section IDs
VERIFY Mermaid blocks have captions
VERIFY recommendation count: quality >= 5, security >= 3
```

#### TASK 6.3 — Evidence Traceability Check
```
VERIFY every entity mentioned in the report was found via at least one Abyss query
MARK unconfirmed inferences explicitly with [INFERRED — not confirmed by KB]
```

---

## 3. OUTPUT SPECIFICATION

### 3.1 File to Create
```
Path: d:\repos\github\spashx\abyss\examples\IlSpy analysis\ilspy-search-analysis.html
Type: Single self-contained HTML file
Encoding: UTF-8
```

### 3.2 HTML Structure Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ILSpy Search Feature Analysis</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>
    /* Professional CSS: navy header, white body, slate tables, accent color */
  </style>
</head>
<body>
  <header><!-- Title, date, author, executive summary --></header>
  <nav><!-- Table of contents with anchor links --></nav>
  <main>
    <section id="executive-summary">...</section>
    <section id="entity-inventory">...</section>
    <section id="search-ui">...</section>
    <section id="search-model">...</section>
    <section id="search-factory">...</section>
    <section id="workflows">
      <!-- Per workflow: class diagram + sequence diagram + CRUD table -->
    </section>
    <section id="crud-reference">...</section>
    <section id="recommendations">...</section>
    <section id="appendix">...</section>
  </main>
  <script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
</body>
</html>
```

### 3.3 Mermaid Block Embedding Pattern
Each diagram MUST be wrapped as:
```html
<div class="mermaid">
classDiagram
  ...
</div>
<p class="diagram-caption">Figure N: [Description]</p>
```

---

## 4. QUALITY GATES

The agent MUST NOT proceed to report generation (Phase 5) unless:

| Gate | Condition |
|---|---|
| QG-1 | At least 8 Abyss queries executed (TASK 1.2) |
| QG-2 | Entity inventory contains ≥ 6 primary entities |
| QG-3 | At least 3 workflows identified with CRUD annotations |
| QG-4 | All 4 Mermaid diagrams drafted (1 class + 3 sequence) |
| QG-5 | Recommendations list has ≥ 5 quality + ≥ 3 security items |

If any gate fails, the agent SHALL loop back to the relevant Phase and gather more data.

---

## 5. ANTI-PATTERNS TO AVOID

1. **DO NOT** invent class names without Abyss evidence.
2. **DO NOT** write generic Mermaid diagrams with placeholder names.
3. **DO NOT** produce a one-size-fits-all report — every section must reference ILSpy-specific code.
4. **DO NOT** skip the Evidence Appendix — traceability is mandatory.
5. **DO NOT** use external CSS files or images — the HTML report must be standalone.
6. **DO NOT** mark the task as complete without verifying the HTML file was written to disk.
7. **DO NOT** produce a short report — depth and detail are required; aim for a comprehensive professional deliverable.

---

## 6. SUCCESS CRITERIA

The task is **complete** when:
- [x] File `ilspy-search-analysis.html` exists in the target directory
- [x] File opens in a browser and all Mermaid diagrams render correctly
- [x] All 9 required sections are present and non-empty
- [x] Every entity mentioned in the report is traceable to an Abyss query result
- [x] Recommendations are specific to ILSpy Search code, not generic
- [x] The report looks professional and is readable without prior ILSpy knowledge
