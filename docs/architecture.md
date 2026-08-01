# Architecture

Data Agent is a local-first agent harness for data analysis.

## Core Ideas

`Skill` defines how a class of analysis should be performed.

`Tool` performs deterministic work such as reading files, running Python, querying DuckDB, rendering charts, and exporting reports.

`Run` is the durable record of one analysis from user request to artifacts.

`Artifact` is any generated output that the UI can render or download: Markdown report, HTML report, notebook, chart, dashboard, table, or run log.

## MVP Flow

```text
User question
  -> Skill router (LLM-driven, deterministic fallback)
  -> Project preflight (context, semantic layer, data profiles)
  -> LLM planning (single conversation: route → execute → synthesize)
  -> Local controlled Python execution (pandas + DuckDB)
  -> Evidence tables and charts (with source provenance)
   -> Visual report artifact (manifest + snapshot) + HTML report / notebook artifacts
  -> Validation gate (15 gates, evidence cross-referencing)
  -> Export package (SHA-256 checksums, import validation)
  -> Memory store (SQLite)
```

## Memory

The SQLite store should eventually hold:

- analysis projects
- project-scoped business context
- dataset records and schemas
- metric definitions
- user preferences
- runs and tool calls
- artifacts and source metadata

Context is selected by analysis project. It should not be treated as one global background shared by every run.

## Sandbox / Code Execution

`DATA_AGENT_GENERATED_CODE_EXECUTION` controls how generated Python code runs:

- `local` (current default): subprocess via `sys.executable`, scrubbed env, output in run directory only
- `disabled`: no execution — runs return a blocked result

**Current path: local controlled execution.**

## Architecture Evolution (2026-06-07)

### LLM-Led Routing
Skill selection is LLM-driven through the planner reading `skills/index.md`.
A deterministic `SkillRouter` with keyword matching serves as fallback when the
LLM is unavailable.

### Evidence Validation
15 validation gates run before delivery, cross-referencing evidence IDs against
actual chart/table IDs in the manifest. Dangling evidence IDs now cause gate
failure. Manifest blocks, not legacy ReportBlock objects, are the validation
surface.

### Artifact Contracts
- `ArtifactManifest` (blocks, charts, tables, cards, sources) + `ArtifactSnapshot`
  (datasets, evidence_map) separate structure from data
- Export packages include SHA-256 checksums for integrity verification
- `import_artifact_package()` validates checksums on import

### Chart Data Fidelity
- `secondary_value` treated as second y-field, not size encoding
- boxPlot quartile fields and heatmap matrix fields preserved through manifest
- Unit and axis labels preserved in chart encodings

### Semantic Layer
- Active layer selection via `select_active_layer()` (prefers `is_active` flag,
  falls back to latest-by-created-at)
- Typed helpers (MetricEntry, DimensionEntry, CaveatEntry) for consistent
  semantic-layer authoring
- Project-scoped routes for list/create/inspect/promote semantic layers

### Testing
- 247 tests covering execution, validation, E2E, manifest, skills, export,
  semantic routes, semantic maturity, isolation, fallback paths, and
  exploratory protocol
- Golden E2E with project context, semantic layer fixture, candidate angles,
  evidence cross-referencing, and export integrity
- Frontend: 12 automated tests (vitest, `bun run test`) covering chart adapters,
  heatmap yFields, secondary y-field, boxPlot, unit/source, and color
- `scripts/demo` — local E2E scenario (project → dataset →
  context → semantic layer → analysis → report → export validation). Run with
  `./scripts/demo` (shell wrapper calling `scripts/_demo.py`).

### Current Non-Goals
- No BI platform or multi-tenant SaaS
- No Docker-first execution route
- No global business context memory (always project-scoped)
- No unsupported claim generation (LLM must cite evidence)

### Known Limitations
- Chart widget rendering is basic (single-chart, no multi-series interaction)
- No streaming/interactive analysis (runs are batch, not real-time)
- Report output is static (no real-time refresh)
- Semantic layer editing is split between ContextModule and SemanticLayerModule tabs
- Checksum fields live in untyped `metadata` dict, not as dedicated ArtifactPackage fields
