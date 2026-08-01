# Visual Report Architecture

Two-layer architecture for generating management-style visual reports from
LLM-authored Markdown analysis.

## Layers

### 1. `md_visual` layer (`renderer_target="md_visual"`)

**Source**: `visual_deck_blocks.py` → `build_visual_deck_blocks()`

Derived reading-surface blocks that restructure prose into scannable visual
surfaces without inventing new claims:

- `executive_storyboard`, `adaptive_story`: section-level visual summaries
- `page_summary`, `insight_banner`: compressed section takeaways
- `next_action_list`: action items extracted from report prose
- `risk_panel`, `data_quality_panel`: caveats and data quality notes
- `decision_matrix`, `forecast_band`: structured decision/forecast views

**Evidence binding**: `source_section` / `source_excerpt` preferred.
`evidence_ids` only when a real match exists (no fallback to first evidence id).

**Origin tags**:
- `block_origin="visual_deck"` → `visual_deck_blocks.py`
- `block_origin="report_plan"` → `artifact_manifest.py` action block

### 2. `evidence_component` layer (`renderer_target="evidence_component"`)

**Sources**:
- `artifact_manifest.py` → chart/table/metric-strip blocks (from `build_artifact_manifest()`)
- `visual_report_planner.py` → `build_visual_report_blocks()` kpi_grid, charts, trend/forecast/delta/risk panels

Chart, table, metric, and evidence-derived blocks that carry real data bindings:

- `kpi_grid`, `metric_change`, `leaderboard_pair`, `composition_panel`
- `chart`, `table`, `metric-strip`
- `trend_panel`, `forecast_band`, `delta_bridge`, `risk_panel`
- `data_quality_panel`, `decision_matrix`

**Evidence binding**: MUST have real `evidence_ids` (chart_id, table_id, card_ids).
Must carry `source_id` for traceability. Snapshot carries `evidence_map` for audit.

**Origin tags**:
- `block_origin="artifact_manifest"` → `build_artifact_manifest()`
- `block_origin="visual_report_planner"` → `build_visual_report_blocks()`

### 3. `appendix` layer (`renderer_target="appendix"`)

**Source**: `artifact_manifest.py` appendix section

Unused charts/tables placed after the main reading flow for reference.
Marked `evidence_priority="appendix"`.

### 4. `narrative` layer

**Source**: `artifact_manifest.py` → markdown blocks from `build_artifact_manifest()`

Raw Markdown prose blocks (`type=markdown`). These are the source text
that md_visual and evidence_component blocks derive from. No `renderer_target`
needed—they are identified by `type == ArtifactBlockType.markdown`.

## Block Fields

| Field | Values | Purpose |
|-------|--------|---------|
| `renderer_target` | `md_visual`, `evidence_component`, `appendix`, `narrative` | Which renderer surface this block targets |
| `block_origin` | `visual_deck`, `artifact_manifest`, `visual_report_planner`, `report_plan`, `reading_flow` | Which module created this block |

Defined in `app/models/schemas.py` as `RENDERER_TARGETS` / `BLOCK_ORIGINS` constants.
Validation gate `validate_layer_tags` enforces allowed values.

## Reading Flow Composition

`compose_reading_flow()` in `visual_report_planner.py` is the single entry point
for final block ordering. No other function may independently reorder blocks.

**Ordering rules**:
1. For each source section: narrative → md_visual → evidence_component
2. Unanchored md_visual blocks go after executive summary
3. Unanchored evidence_component blocks go to appendix
4. All appendix blocks at the end

Section matching uses `normalize_section_title()` from `visual_deck_blocks.py`
to handle numbering differences (e.g., "A3. 渠道趋势" matches "渠道趋势").

## Evidence Binding Rules

1. Quantitative md_visual blocks: `evidence_ids` only set when a real match exists
   via token matching. No fallback to first evidence id.
2. Evidence_component blocks: MUST have real `evidence_ids` (chart/table/card ids).
3. Source binding: `attach_stable_source_ids()` links charts/tables to manifest
   sources. No fallback: `len(source_ids) == 1` does NOT auto-assign.
4. Deduplication: `dedupe_blocks()` uses `(type, title, source_section, renderer_target, evidence_ids)` as key to preserve different-layer blocks with same title.

## Validation Layers

| Layer | Gates | What it checks |
|-------|-------|----------------|
| md_visual | `markdown_content_preservation`, `visual_section_coverage` | Every substantive line preserved; high-signal sections have visual treatment |
| evidence_component | `evidence_coverage`, `chart_contracts`, `chart_encoding`, `source_metadata` | Real evidence ids, valid chart types, source traceability |
| overall | `visual_report_richness`, `table_dominance`, `core_conclusion_visual_support`, `layer_tags` | Table ratio ≤30%, first screen not dominated by tables, valid layer tags |
| audit | `source_safety`, `sensitive_payload`, `renderability` | No secrets in artifacts, all artifacts renderable |

## Frontend Display Modes ✅ (implemented `1657054`)

| Mode | Shows | Status |
|------|-------|--------|
| 阅读 (Reading) | narrative + md_visual + key evidence_component in reading flow order | ✅ |
| 证据 (Evidence) | evidence_component + appendix blocks with source drawer | ✅ |
| 审计 (Audit) | All blocks with renderer_target/block_origin/evidence_ids metadata, manifest, snapshot | ✅ |
| 导出 (Export) | Selected layers per export format (not yet per-mode) | ⚠️ |

Implementation: `ManifestReportWidget` in `ArtifactModule.tsx` — `filterBlocksByMode()` + view mode toggle.

## File Map

| File | Role |
|------|------|
| `visual_deck_blocks.py` | Builds md_visual blocks from Markdown + manifest evidence |
| `visual_report_planner.py` | Builds evidence_component blocks from cards/tables/charts; `compose_reading_flow()` |
| `artifact_manifest.py` | Builds narrative + evidence_component + appendix blocks; `build_artifact_manifest()` |
| `orchestrator.py` | Orchestrates composition: calls build functions, then `compose_reading_flow()` |
| `validation.py` | Layer-aware validation gates |
| `schemas.py` | `RENDERER_TARGETS`, `BLOCK_ORIGINS`, `ArtifactBlock` |
| `ArtifactModule.tsx` | Frontend layer-aware renderer with reading/evidence/audit modes |
| `reportLayout.ts` | `prepareReportBlocks()` — layer-aware sanitize vs legacy reorder |
