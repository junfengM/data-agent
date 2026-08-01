# Deterministic Tool Contracts

Each tool in `server/app/tools/` is a deterministic, non-LLM computation unit. This
document defines the contract for each tool: what it accepts, what it produces, what
side effects it has, and how it fails.

---

## 1. execution.py — Analysis Code Execution

**Purpose**: Run LLM-generated Python analysis code through a configurable runner.

### Execution Modes

| Mode | Description | Security |
|---|---|---|
| `disabled` (default) | No execution; returns blocked result | Safe |
| `local-dev` (or `local`) | Local subprocess with scrubbed env | Development only, NOT a security boundary |
| `sandbox` | Isolated sandbox | Placeholder — no backend configured |

### Input Schema

| Parameter | Type | Required | Description |
|---|---|---|---|
| `code` | `str` | yes | Python source code to execute |
| `run_dir` | `Path` | yes | Isolated output directory (per run) |
| `dataset_paths` | `list[Path]` | yes | Dataset files to copy into the run directory and expose to generated code |
| `timeout_seconds` | `int` | no (default: 120) | Execution time limit |
| `generated_code_execution` | `str` | yes | Mode: `"disabled"`, `"local-dev"`, `"local"`, or `"sandbox"` |

### Generated Code Environment

When local execution is enabled, generated code receives:

| Name | Type | Description |
|---|---|---|
| `dataset_paths` | `list[str]` | Actual copied dataset file paths, ready to pass to `pandas.read_csv/read_excel` |
| `dataset_path_variables` | `list[str]` | Safe generated variable names for each dataset path |
| `dataset_vars` | `dict[str, str]` | Mapping from safe variable name to actual copied dataset path |
| `<safe_dataset_name>` | `str` | One variable per dataset path for backward-compatible direct access |

Generated code should prefer `dataset_paths[0]` over `eval(dataset_paths[0])`.

### Output Schema

`ExecutionResult` (frozen dataclass):
| Field | Type | Description |
|---|---|---|
| `returncode` | `int` | Process exit code |
| `stdout` | `str` | Captured standard output |
| `stderr` | `str` | Captured standard error |
| `tables` | `list[dict]` | CSV/JSON table outputs: `{name, path, rows, columns[], preview[]}` |
| `charts` | `list[dict]` | Chart outputs: `{name, path, type, render_mode, asset_path}` |
| `generated_files` | `list[Path]` | Other new output files created during execution |

### Side Effects

- Creates files in `run_dir/` (tables, charts, other outputs)
- Copies dataset files into `run_dir/datasets/`
- Spawns a `subprocess` with `sys.executable`

### Allowed Files / Paths

- **Read**: Dataset copies under `run_dir/datasets/` are exposed to generated code
- **Write**: Output discovery only reports bounded non-symlink files under `run_dir/`
- **local-dev mode caveat**: the subprocess is not a filesystem or network sandbox; this contract describes intended tool behavior, not a security boundary

### Failure Modes

| Condition | Behavior |
|---|---|
| `generated_code_execution == "disabled"` | Returns blocked result, no execution |
| `generated_code_execution == "sandbox"` | Returns blocked result: "no sandbox backend available" |
| `generated_code_execution == "local-dev"` (or `"local"`) | Executes in subprocess with scrubbed env |
| Code timeout | Process killed after `timeout_seconds` |
| Syntax error in user code | Captured in stderr |
| Import error | Captured in stderr |
| Missing dataset paths | User code receives empty list |
| Oversized or excessive outputs | Skipped during artifact discovery |

### Produced Artifacts

- `ArtifactType.table` for each detected CSV/JSON table output
- `ArtifactType.chart` for each detected chart output (HTML/PNG/JPG/SVG/Plotly JSON)

---

## Runtime Event Stream — Planner Observability

**Purpose**: Provide a human-reviewable live trace for analysis runs without changing deterministic tool execution. The frontend consumes these events through the run SSE stream and translates them into the Chinese "分析过程" timeline.

### `llm_request_started`

The planner emits this before each model call.

Key fields:

| Field | Type | Description |
|---|---|---|
| `iteration` | `int` | Planner loop iteration |
| `phase` | `str` | `analysis`, `finalize`, or related phase |
| `message_count` | `int` | Number of messages sent to the model |
| `prompt_chars` | `int` | Total direct message content chars |
| `context_budget` | `dict` | Role-level and tool-result budget summary |
| `available_tools` | `list[str]` | Tool names exposed to the model for this call |
| `prompt_snapshot` | `dict` | Bounded prompt/message preview for review |

`prompt_snapshot` schema:

| Field | Type | Description |
|---|---|---|
| `message_count` | `int` | Total messages in the model request |
| `included_message_count` | `int` | Messages included in the snapshot |
| `omitted_message_count` | `int` | Middle messages omitted when the request is long |
| `total_content_chars` | `int` | Sum of message content chars |
| `head_chars` / `tail_chars` | `int` | Per-message preview bounds |
| `messages` | `list[dict]` | Included messages with `index`, `role`, `content_chars`, `content_preview`, and `tool_calls` |

`content_preview` and tool-call `arguments_preview` use `{chars, head, tail, truncated}`. Tool-call argument previews are converted to readable JSON with `ensure_ascii=False` when the argument string is valid JSON. This stream is for local development and prompt-quality review; it is bounded for UI/runtime size, not a secrecy boundary.

### High-Value Frontend Summaries

The Run module should keep the timeline summary user-facing and action-oriented:

| Event | Summary Contract |
|---|---|
| `llm_request_started` | Show iteration, phase, message count, and expandable prompt snapshot |
| `llm_request_completed` | Show next selected tool(s), finish reason, latency, and compact token usage |
| `code_execution_completed` | Show success/failure plus table/chart output counts and key stdout/stderr |
| `validation_completed` | Show pass ratio, failure count, and warning count when available |
| `planner_final_output_format_repair_*` | Show finalizer recovery state and repaired report size |
| `planner_final_payload_parsed` | Show report length, chart/table specs, candidate angles, and quality flags |

### LLM Tuning Log

The task replay surface exposes a dedicated LLM tuning view and export built from
the same persisted runtime events:

```text
GET /api/runs/<run_id>/trace/llm
GET /api/runs/<run_id>/trace/llm/export
```

The payload is intended for prompt/model/runtime tuning rather than general run
replay. It groups observable events by planner iteration and includes:

| Field | Description |
|---|---|
| `summary.request_count` | Number of model-call rounds reconstructed from events |
| `summary.total_prompt_tokens` / `total_completion_tokens` | Provider usage totals when available |
| `summary.total_latency_ms` | Sum of model response latencies |
| `summary.length_truncation_count` | Count of `finish_reason == "length"` responses |
| `summary.tool_request_count` / `tool_failure_count` | Tool decision and failure counts |
| `summary.max_estimated_context_chars` | Highest estimated prompt/context size |
| `rounds[]` | Per-iteration phase, model, context budget, prompt snapshot, finish reason, usage, tool decisions, and response preview |
| `tuning_notes[]` | Human-readable tuning hints for truncation, tool failures, high context, missing snapshots, and forced finalization |

The frontend displays the same information as a visual LLM call chain plus
expandable per-round details. Hidden chain-of-thought is not recorded; prompt and
response previews are bounded observable payload snippets and are redacted by key
name during export.

---

## 2. preflight.py — Project Preflight Envelope

**Purpose**: Build a compact context snapshot before analysis: project metadata, semantic
layer, dataset profiles, context gaps, and obligations.

### Key Functions

| Function | Signature |
|---|---|
| `load_semantic_layer(path)` | `Path → SemanticLayer` |
| `load_source_category_config(path)` | `Path → list[SourceCategoryConfig]` |
| `derive_semantic_layer(profiles)` | `list[Any] → SemanticLayer` |
| `select_active_layer(layers)` | `list[dict] → dict \| None` |
| `build_preflight_envelope(...)` | Multiple params → `ProjectPreflight` |
| `preflight_to_markdown(preflight)` | `ProjectPreflight → str` |

### Input Schema (build_preflight_envelope)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project` | `AnalysisProject \| None` | yes | Selected project |
| `project_contexts` | `list[ProjectContext]` | yes | Scoped context items |
| `semantic_layer` | `SemanticLayer` | yes | Parsed semantic layer |
| `profiles` | `list[DatasetProfile]` | yes | Dataset profiles |
| `source_routing` | `dict \| None` | no | Source preferences |
| `onboarding_progress` | `dict \| None` | no | Onboarding state |
| `source_category_config` | `list \| None` | no | Category configs |
| `project_layers` | `list[dict] \| None` | no | Registered layer records |

### Output Schema

`ProjectPreflight` dataclass:
| Field | Type | Description |
|---|---|---|
| `project_id` | `str` | Project ID or `""` |
| `project_name` | `str` | Project name or `"No project"` |
| `project_contexts` | `list[dict]` | Context items |
| `semantic_layer` | `SemanticLayer` | Layer with metrics/dimensions |
| `profiles` | `list[dict]` | Dataset summaries |
| `context_gaps` | `list[str]` | Missing context warnings |
| `source_routing` | `dict` | Source preferences |
| `onboarding_progress` | `dict` | Onboarding status |
| `obligations` | `list[str]` | Required validations |
| `active_semantic_layer_meta` | `dict \| None` | Active layer id/name |

### Side Effects

- Reads YAML files from disk
- Reads dataset files for profiling

### Failure Modes

| Condition | Behavior |
|---|---|
| Missing semantic-layer YAML | Returns empty `SemanticLayer()` |
| Missing source category config | Returns empty list |
| No project selected | Returns `project_id=""`, `project_name="No project"` |
| No layers registered | `active_semantic_layer_meta` is `None` |

### Produced Artifacts

- None directly (used as input to orchestrator)

---

## 3. validation.py — Validation Gates

**Purpose**: Run pre-delivery quality checks on analysis output.

### Key Functions

24 validation gates, each returning `ValidationResult(gate_id, passed, message, severity, details)`.

Gates include: preflight, evidence_coverage, markdown_content_preservation,
visual_section_coverage, evidence_references, report_quality,
visual_report_richness, table_dominance, visual_evidence_links,
core_conclusion_visual_support, chart_contracts, chart_contract_compatibility,
context_caveats, project_context_coverage, semantic_ambiguity,
renderability, chart_encoding, source_safety, sensitive_payload,
completion_mode, source metadata checks, and layer_tags.

| Gate | Gate ID | Checks |
|---|---|---|
| `validate_preflight` | `preflight` | Preflight completed |
| `validate_evidence_coverage` | `evidence_coverage` | Key claims have evidence |
| `validate_evidence_references` | `evidence_references` | Block evidence_ids reference existing ids |
| `validate_source_metadata` | `source_metadata` | Tables/charts have source info |
| `validate_source_metadata_on_evidence` | `source_metadata_on_evidence` | Evidence items have provenance |
| `validate_schema_compliance` | `schema_compliance` | Report blocks follow schema |
| `validate_layer_tags` | `layer_tags` | `renderer_target` and `block_origin` use allowed values |
| `validate_chart_contracts` | `chart_contracts` | Chart types are valid |
| `validate_chart_contract_compatibility` | `chart_contract_compat` | Chart type+intent compatible |
| `validate_context_caveats` | `context_caveats` | Missing context surfaced |
| `validate_project_context_coverage` | `project_context_coverage` | Project context used |
| `validate_renderability` | `renderability` | Artifacts renderable |
| `validate_chart_encoding` | `chart_encoding` | Chart encodings correct |
| `validate_source_safety` | `source_safety` | No unsafe sources |
| `validate_sensitive_payload` | `sensitive_payload` | No sensitive data leaked |
| `validate_completion_mode` | `completion_mode` | Delivery mode is set |

### Orchestrator

`run_validation_gates()` calls all 24 gates and returns `list[ValidationResult]`.

### Input Schema (per gate)

Each gate accepts specific parameters relevant to its check. Common parameters:
- `step_results: list[dict]` — Execution step outputs
- `report_md: str` — Report markdown
- `blocks: list[dict]` — Manifest blocks
- `plan_caveats: list[str]` — Planner caveats
- `profiles: list[Any]` — Dataset profiles
- `artifacts: list[dict]` — Generated artifacts

### Output Schema

`ValidationResult`:
| Field | Type | Description |
|---|---|---|
| `gate_id` | `str` | Gate identifier |
| `passed` | `bool` | Whether the gate passed |
| `message` | `str` | Human-readable result |
| `severity` | `str` | `"pass"`, `"warning"`, or `"fail"` |
| `details` | `dict` | Extra context |
| `fix_hint` | `str \| None` | Actionable repair guidance for the owner layer |
| `owner_layer` | `str \| None` | Responsible layer: `planner`, `execution`, `manifest`, `visual_deck`, `reading_flow`, `frontend`, `export`, `semantic_layer` |
| `related_block_ids` | `list[str]` | Block ids related to this gate failure |
| `related_evidence_ids` | `list[str]` | Evidence ids with issues (e.g., dangling refs) |
| `can_auto_repair` | `bool` | Whether this failure is auto-repairable |

### Run Mode → Gate Behavior

| Mode | Gate Behavior |
|---|---|
| `full` | All gates active. Evidence, chart, and visual richness gates enforced. |
| `plan_only` | Evidence-related gates skipped: `evidence_coverage`, `source_metadata*`, `visual_evidence_links`, `chart_contracts*`, `chart_encoding`, `core_conclusion_visual_support`, `visual_report_richness`, `table_dominance`. |
| `preflight_only` | Validation not invoked (run exits before report generation). |

### Severity Mapping → Run Status

| Gate Result | Run Status |
|---|---|
| All passed | `completed` |
| Any warning, no fail | `completed_with_warnings` |
| Any fail | `failed` |

### Failure Modes

| Condition | Behavior |
|---|---|
| Missing evidence on claim blocks | `warning` or `fail` severity |
| Missing source metadata on chart/table | `warning` severity |
| Invalid chart type | `fail` severity |
| No delivery mode set | `fail` severity |
| Invalid renderer layer tags | `fail` severity |

### Produced Artifacts

- Validation results stored in run_log artifact data as `validation_results`
- Validation summary stored as `ToolCall(name="validation_gate")`

---

## 3b. semantic_validation.py — Semantic Layer Validation & Merge Precheck

**Purpose**: Detect ambiguous/conflicting metric definitions and precheck layer merges.

### Key Types

| Type | Description |
|---|---|
| `SemanticAmbiguity` | Detected conflict with `metric_name`, `conflict_type`, `severity` (blocker/warning/info), `repair_action`, `suggested_resolution`, `affected_metric_indices` |
| `SemanticMergePreview` | Precheck result: `can_confirm`, `blockers`, `warnings`, `would_replace/add/keep` |

### Detection Rules (6 rules + severity)

| Rule | Severity | Repair Action |
|---|---|---|
| `duplicate_name` (same name, same formula) | `warning` | `merge_duplicate` |
| `duplicate_name` (same name, different formula) | `blocker` | `rename_metric` |
| `conflicting_formula` | `blocker` | `rename_metric` |
| `conflicting_aggregation` | `blocker` | `rename_metric` |
| `conflicting_grain` | `blocker` | `split_by_grain` |
| `conflicting_source` | `blocker` | `split_by_source` |
| `near_duplicate` | `warning` | `needs_user_confirmation` |

### Canonicalization Helpers

| Function | Purpose |
|---|---|
| `normalize_metric_name(name)` | Lower-case, trim, normalize parens/dashes |
| `normalize_formula(formula)` | Strip whitespace, lower-case, normalize parens |
| `canonical_metric_key(metric)` | `source_table::normalized_name` for merge lookup |
| `extract_metric_signature(metric)` | Full comparable signature dict |

### Merge Precheck Contract

| Function | Returns |
|---|---|
| `precheck_semantic_layer_merge(existing_layer, incoming_payload)` | `SemanticMergePreview` |

Performs two checks:
1. Runs `detect_semantic_ambiguities` on merged (existing + incoming) metrics
2. Cross-source name conflict detection for same-name metrics from different sources

| Condition | Result |
|---|---|
| No blockers | `can_confirm=True` |
| Has blockers | `can_confirm=False` — confirm returns 409 |
| Has warnings | `can_confirm=True` — warnings returned in response |

### API Contract

`POST /api/projects/{project_id}/semantic-drafts/{draft_id}/confirm?dry_run=true`
- Returns `SemanticMergePreview` without writing
- Status 200 with `can_confirm`, `blockers`, `warnings`, `would_replace/add/keep`

`POST /api/projects/{project_id}/semantic-drafts/{draft_id}/confirm`
- Runs precheck first
- Returns 409 on blockers (with detail including suggested resolutions)
- On success, merges and writes, returns `warnings` in response

---

## 4. exports.py — Artifact Package Export

**Purpose**: Bundle manifest, snapshot, and metadata into a JSON export file with integrity checksums.

### Input Schema

`export_artifact_package()`:
| Parameter | Type | Required | Description |
|---|---|---|---|
| `run_id` | `str` | yes | Run identifier |
| `title` | `str` | yes | Report title |
| `question` | `str \| None` | no | Original question |
| `project_id` | `str \| None` | no | Project identifier |
| `manifest` | `ArtifactManifest` | yes | Structured manifest |
| `snapshot` | `ArtifactSnapshot` | yes | Bounded data snapshot |
| `output_dir` | `Path \| None` | no | Output directory (default: `workspace/exports/`) |
| `candidate_angles` | `list[dict] \| None` | no | Analysis angles |

### Output Schema

Returns `Path` to generated JSON file. Package contents:

| Key | Type | Description |
|---|---|---|
| `package_version` | `int` | Schema version (currently 1) |
| `title` | `str` | Report title |
| `generated_at` | `str` | ISO timestamp |
| `project_id` | `str \| null` | Project identifier |
| `question` | `str \| null` | Original question |
| `manifest` | `object` | Full structured manifest |
| `snapshot` | `object` | Full data snapshot |
| `metadata` | `object` | Checksums, counts, app version |

### Side Effects

- Creates directory `output_dir/` if it doesn't exist
- Writes JSON file to disk

### Failure Modes

| Condition | Behavior |
|---|---|
| Output directory unwritable | Raises `OSError` |
| Manifest too large | No explicit limit — may produce large file |

---

## 5. AnalysisRequest.run_mode — Execution Mode Contract

**Purpose**: Control how far the orchestrator proceeds before stopping.

### Schema

`AnalysisRequest.run_mode: Literal["full", "preflight_only", "plan_only"]` (default `"full"`)

### Mode Behavior

| Mode | LLM Calls | Code Execution | Report Artifacts | Validation |
|---|---|---|---|---|
| `full` | Yes (Planner) | Yes (via `execute_code` tool) | markdown, visual_report, html, notebook, run_log | All 24 gates |
| `plan_only` | Yes (Planner) | **No** — stub returns `returncode=0, status="skipped"`, tool hidden from LLM | markdown (plan draft), run_log | Evidence gates skipped |
| `preflight_only` | **No** | **No** | dataset profile table/chart, run_log | Not invoked |

### plan_only Internal Semantics

- `Planner.run_analysis(require_evidence=False)` sets `effective_data_backed = False`
- `_available_tools()` hides `execute_code` and `save_semantic_finding` from LLM
- `evaluate_attempt_feedback` and `_evaluate_payload` called with `effective_data_backed=False`
- No `_must_execute_prompt` hard stops — LLM can produce plan draft without code execution
- Stub executor returns `returncode=0, status="skipped"` — not counted as failure by `_has_successful_evidence`

### preflight_only Internal Semantics

- Exits after preflight envelope is built
- Marks `diagnosis` and `report` workflow steps as completed with skip message
- Returns `run.status = "completed"`

---

## 6. evidence_linking.py — Evidence-to-Block Binding

### Key Functions

| Function | Returns |
|---|---|
| `tokenize(text)` | `set[str]` — lowercase tokens, min length 2 |
| `score_evidence_item(block_text, item)` | `float` — weighted match score |
| `link_evidence(block_text, evidence_items, top_k, min_score)` | `list[str]` — evidence ids only |
| `link_evidence_with_explanations(block_text, evidence_items, top_k, min_score)` | `(list[str], list[dict])` — ids + link metadata |

### EvidenceLink Schema

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `str` | Matched chart or table id |
| `method` | `str` | `"text_similarity"` |
| `score` | `float \| None` | Match score (weighted token overlap) |
| `matched_terms` | `list[str]` | Tokens shared between block text and evidence title |
| `reason` | `str \| None` | Human-readable explanation of match |

### Scoring Dimensions

| Dimension | Weight | Description |
|---|---|---|
| Name token overlap | 3.0 | Shared tokens between block text and evidence title |
| Source/path overlap | 1.5 | Shared tokens with evidence source path |
| Explicit id match | 5.0 | Evidence id appears literally in block text |
| Dataset match | 2.0 | Dataset name tokens match block text |
| Spec id match | 3.0 | Chart spec id appears literally in block text |

### No-Fallback Rule

`link_evidence` and `link_evidence_with_explanations` return empty results when no item scores above `min_score` (default 0.5). There is no fallback binding to the first available evidence item. This is intentional: wrong evidence is worse than no evidence.
