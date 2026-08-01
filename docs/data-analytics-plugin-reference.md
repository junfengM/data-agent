# Data Analytics Plugin Reference Decisions

This file records which Data Analytics plugin concepts should be adopted by this local Data Agent project.

## 1. `mcp/server.cjs`

Decision: **Adopt the contracts, not the MCP server shape.**

The plugin MCP server provides:

- `validate_artifact`
- `render_artifact`
- `export_artifact_package`
- `render_chart`
- `render_table`

Important ideas to keep:

- Validate before render.
- Separate artifact `manifest` from bounded `snapshot`.
- Use `blocks` as the report/dashboard reading order.
- Keep reusable cards, charts, tables, sources, and datasets as structured objects.
- Enforce chart/table field contracts and reject legacy or unsafe shapes.
- Bound payload sizes, row counts, source text, and unsafe field names.
- Export deployable packages from validated artifact payloads instead of hand-rolled one-off HTML.

Local adaptation:

- We do **not** need an MCP server for the default app.
- We do need an internal artifact runtime:
  - `validate_artifact_payload()`
  - `render_report/dashboard` in React
  - `render_chart` and `render_table` from structured specs
  - `export_artifact_package()` for a portable static/deployable bundle
- Future package export should preserve the app artifact runtime and serve:
  - artifact manifest
  - bounded snapshot
  - source metadata
  - report/dashboard assets

## 2. `AGENTS.md`

Decision: **Create a local repo-level `AGENTS.md`.**

The plugin `AGENTS.md` is mostly an engineering and UX contract. It records what future agents must preserve when changing the plugin.

Local adaptation:

- Add an `AGENTS.md` for this repo that tells Codex/DeepSeek-style agents:
  - keep context project-scoped
  - preserve skill-driven, tool-backed, artifact-first architecture
  - use local controlled execution, not Docker as a required path
  - run backend/frontend/test validation before claiming completion
  - update `docs/progress.md` and `docs/reviews.md`
  - do not introduce global business memory
  - preserve Chinese modular UI

## 3. `skills/index/SKILL.md`

Decision: **Build a real local router skill.**

The plugin index skill is not just a README. It defines run order:

1. Run user-context preflight.
2. Apply semantic-layer lookup.
3. Apply source discovery and access guardrails.
4. Choose inline vs report mode.
5. Pick the smallest useful skill chain.
6. Load focused skill bodies before analysis.
7. Apply completion gates before final delivery.

Current local project status:

- There is `skills/index.md`.
- Current routing is keyword-based and shallow.
- Auxiliary skill loading exists, but route reasoning is still minimal.

Local adaptation:

- Upgrade `skills/index.md` into the authoritative routing contract.
- Planner/run log should expose:
  - response mode: inline/report/dashboard/notebook
  - primary skill
  - auxiliary skills
  - semantic layer used
  - required tools
  - expected artifacts
  - validation gates

## 4. `user-context`

Decision: **Adopt as project preflight + semantic-layer registry, not global memory.**

The plugin `user-context` owns:

- durable source-routing preferences
- onboarding/setup status
- semantic-layer registry
- pre-answer/preflight envelope
- final obligations and context-gap guidance

Important restriction:

- It is not general memory.
- It does not store arbitrary user facts.
- Semantic meaning belongs in semantic layers, not loose notes.

Local adaptation:

- Because this project is project-scoped, `user-context` should become `project_preflight`.
- Each run should load a compact preflight envelope:
  - selected project
  - project contexts
  - semantic layers
  - dataset profiles/schema summaries
  - missing definitions or context gaps
  - source and validation obligations
- The app should expose onboarding/setup only for the current project or workspace, not as global Data Analytics memory.

## 5. Artifact Manifest + Snapshot Contract

Decision: **Separate artifact structure (manifest) from bounded data (snapshot).**

The plugin defines a strict separation:

```
manifest:  { version, title, blocks[], charts[], tables[], cards[], sources[] }
snapshot:  { version, status, datasets: { [id]: Row[] }, accessIssues[] }
```

Current local project flattens everything into `Artifact { type, title, content, data }` — structure and data are mixed. This blocks:
- Structured block composition (blocks define reading order, not free-form content)
- Bounded snapshot validation (row/cell/size limits)
- Chart encoding contracts (x/y/color/facet encodings per chart)
- Source metadata tracking (SQL, tables_used, filters, metric_definitions)
- Deployable package export

Local adaptation:
- Create `ArtifactManifest` and `ArtifactSnapshot` Pydantic models
- Manifest.blocks[] drives report reading order (markdown | metric-strip | chart | table)
- Snapshot.datasets contains bounded row arrays, NOT column+rows objects
- Each chart block references manifest.charts[], which declares encodings (x.field, y.field, color.field)
- Each table block references manifest.tables[], which declares columns (field, label, format)
- Validation gate checks manifest↔snapshot cross-references BEFORE rendering

## 6. Chart Contract (19 Canonical Types)

Decision: **Adopt the full canonical chart type set and encoding system.**

Plugin defines 19 chart types with per-type capabilities:

| Category | Types |
|---|---|
| Trend | line, area, stackedArea, sparkline |
| Comparison | bar, horizontalBar, stackedBar, stackedBar100, horizontalStackedBar, horizontalStackedBar100 |
| Distribution | histogram, boxPlot |
| Part-to-whole | pie |
| Relationship | scatter, heatmap |
| Specialized | leaderboard, funnel, waterfall |

Each chart declares encodings: x, y, color, lineStyle, size, facet, label, tooltip.
Charts have intents (trend, comparison, composition, distribution, relationship, funnel) that map to compatible types.

Current local project has 5 basic types (bar, line, area, scatter, pie) with simple x/y fields — no encodings, no intents, no capabilities matrix.

Local adaptation:
- Define `SUPPORTED_CHART_TYPES` matching the plugin's canonical set
- Add `ChartEncoding` model with x/y/color/size/facet fields
- Add chart intent → compatible types mapping
- Frontend ChartRenderer needs to handle new types (leaderboard, funnel, waterfall, boxPlot, heatmap)
- Add `chart_contract.py` for Python-side validation (mixed-scale, mixed-metric detection)

## 7. Skill Depth And Sub-Specifications

Decision: **Expand skills from 20-80 lines to 100+ lines with explicit phase gates and output contracts.**

Plugin skills have:
- 6-10 explicit phases per skill, each with entry/exit conditions
- Output contracts (exactly one delivery mode, exactly one audience spec, required structure elements)
- Sub-specification files for audience/mode variants (e.g., executive-report.md, technical-report.md)
- Bundled Python scripts that skills reference directly
- Mandatory `$validate-data` pass before handing off to `$build-report`

Current local skills are 20-80 lines, flat, with no sub-files or script references.

Key gaps per skill:

| Skill | Plugin Depth | Local State |
|---|---|---|
| product-business-analysis | 141 lines, 6 phases + $gather-context, $design-kpis, $validate-data | ~40 lines |
| metric-diagnostics | 130 lines, 6 phases + automated calc validation | ~50 lines |
| build-report | 207 lines, 10 phases + 3 sub-specs + 10 QA checks | ~60 lines |
| validate-data | 190 lines, 8-section checklist with confidence scoring | ~100 lines |
| visualize-data | Needs analysis | ~50 lines |

Local adaptation:
- Expand each skill to 100+ lines with explicit phase structure
- Add output contracts to each skill (what must be produced, in what format)
- Add `$validate-data` checkpoint before report generation in analysis skills
- Add `$chart-rules` compliance check in visualization skills
- Keep sub-specifications inline for now (sub-files add complexity without clear benefit at current scale)

## 8. Source Query Contract

Decision: **Standardize source.query structure across all artifacts.**

Plugin defines a canonical source shape:

```json
{
  "source": {
    "id": "...",
    "label": "...",
    "query": {
      "engine": "databricks",
      "sql": "SELECT ... FROM example.analytics.fact_revenue",
      "description": "Human-readable query summary",
      "tables_used": ["example.analytics.fact_revenue"],
      "filters": ["date_window: 2026-Q1"],
      "metric_definitions": ["ARR = SUM(revenue) WHERE status='active'"],
      "executed_at": "2026-06-07T..."
    }
  }
}
```

Current local project has minimal source metadata (path, filename) — no SQL, no tables_used, no metric_definitions.

Local adaptation:
- Add `SourceQuery` model with all plugin fields
- Update dataset profile to include source metadata
- Orchestrator should capture SQL/code provenance in step results
- Report blocks should reference source metadata

## 9. Skill-to-Tool Binding

Decision: **Skills must reference executable tools, not just describe concepts.**

Plugin skills include references to deterministic Python scripts:
- `scripts/data_analytics_preflight.py`
- `scripts/validate_user_context_preflight.py`
- `scripts/report_to_google_doc_plan.py`

These scripts are the **authoritative implementations** of the skill's core logic. The LLM reads the skill for workflow guidance, but execution goes through these scripts.

Current local project has tools in `server/app/tools/` but skills don't reference them — they describe what to do conceptually, leaving implementation to the LLM.

Local adaptation:
- Add tool reference sections to each skill: "Available Tools: preflight.py, validation.py, execution.py"
- Skills should specify which tool to call for each phase, not just describe the phase
- This makes skill behavior testable and auditable

## Gap Priority Matrix (2026-06-07 Plugin Analysis)

| Priority | Item | Effort | Impact | Status |
|---|---|---|---|---|
| P0 | Manifest + snapshot separation | Large | Foundation for all artifacts | → NEXT |
| P0 | Chart contract (19 types + encodings) | Large | Foundation for visualization | → AFTER |
| P1 | Skill depth expansion (100+ lines) | Medium | Better analysis quality | → AFTER |
| P1 | Source query contract | Medium | Audit trail, reproducibility | → AFTER |
| P1 | Skill-to-tool binding | Medium | Deterministic execution | → AFTER |
| P2 | Design System (DESIGN.md + tokens) | Medium | Visual consistency | → LATER |
| P2 | Artifact package export | Large | Deployable sharing | → LATER |
| P3 | Onboarding state machine | Medium | User experience | → LATER |
| P3 | Multi-format report export | Large | Enterprise feature | → LATER |

## Adoption Order (Updated)

Completed:
1. ✅ Local `AGENTS.md`
2. ✅ Local agent manifest
3. ✅ Upgrade `skills/index.md` into a real routing contract
4. ✅ Project preflight envelope
5. ✅ Semantic-layer registry and schema
6. ✅ Project isolation (no-project leakage fix)

Next:
7. **P0: Artifact manifest + snapshot separation**
8. **P0: Chart contract (19 canonical types + encodings)**
9. P1: Skill depth expansion
10. P1: Source query contract
11. P1: Skill-to-tool binding
12. P2: Design System
13. P2: Artifact package export

