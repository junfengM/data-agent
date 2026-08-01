# Recommended Plan

This plan prioritizes building a useful Codex/Data Analytics-style analysis harness first, then refining it through real usage.

## Phase 1: Codex/Data Analytics Foundation

Recommendation: do this first and keep it intentionally close to the Data Analytics plugin mindset.

Build the basic harness shape:

- agent manifest
- skill router
- editable Markdown skills
- model config for OpenAI and DeepSeek
- persistent memory store
- uploaded CSV/Excel datasets
- source-backed run records
- artifact registry
- Markdown, HTML, notebook, table, chart, dashboard, and run-log artifact types

Done when:

- a versioned manifest declares capabilities, skills, tools, artifact types, execution mode, and validation gates
- a run has a durable ID
- a run stores selected skill, input question, datasets, tool calls, artifacts, and caveats
- the UI can render artifacts separately from chat text

## Phase 2: Project-Scoped Context And Memory

Recommendation: make this the next serious feature, because it is one of the main reasons for building the tool.

Add project-scoped context. This is not a single global background. A workspace can contain multiple analysis projects, and each project owns its own context:

- business background
- metric definitions
- common dimensions
- reporting preferences
- audience and tone preferences
- historical runs
- saved dataset schemas
- recurring caveats and known data issues

Done when:

- the user can create, switch, edit, and archive analysis projects in the UI
- each run belongs to one selected project
- each run automatically receives that project's context
- reports cite which context and metric definitions were used

## Phase 2.5: Semantic Layer

Recommendation: add this once project-scoped context exists, because repeated analysis needs stable business meaning, not just free-form notes.

Add semantic-layer support:

- canonical metric definitions
- dimensions and grains
- source files/tables and source precedence
- filters, joins, caveats, and known data issues
- reusable query/code patterns
- project-level semantic-layer registry

Done when:

- a project can store structured metric and dimension definitions
- planner prompts receive relevant semantic-layer entries before generating code
- reports cite which metric definitions and semantic-layer assumptions were used
- conflicting or missing definitions become caveats instead of silent assumptions

## Phase 3: Real LLM Planning

Recommendation: connect the model after the run/artifact/context contracts are stable.

Add planner and orchestration behavior. The LLM should act as the agent's cognitive orchestration layer:

- recognize user intent and route to the right primary skill
- load auxiliary skills when the task needs them, such as chart rules for visualization
- read dataset profile and project-scoped context
- identify missing context, metric definitions, time windows, or caveats
- produce a bounded analysis plan
- choose deterministic tools and write Python/DuckDB code for execution
- score open-ended candidate angles by impact, confidence, actionability, novelty, relevance, and data sufficiency
- synthesize findings from tool outputs
- assemble structured report blocks that link claims to evidence
- quality-check for unsupported conclusions, weak data, chart misuse, and metric ambiguity

Done when:

- DeepSeek/OpenAI can generate a plan
- the plan is visible in the run log
- model output is constrained by the selected skill and output contract
- selected primary and auxiliary skills are visible in the run log
- every key report claim can be traced back to tool output, table data, chart data, or project context

## Phase 4: Local Controlled Execution

Recommendation: do not require Docker for the default local workflow. Use a local controlled Python runner with explicit opt-in for generated-code execution.

Add execution controls:

- explicit execution enablement or UI acknowledgement
- scrubbed environment variables
- run-directory workspace
- timeout
- allowed output collection under the run directory
- captured stdout/stderr
- deterministic pandas/DuckDB smoke checks
- clear warning when generated-code execution is disabled or unavailable

Done when:

- generated analysis code runs only after explicit local enablement
- the runner uses the configured Python environment with required analysis dependencies
- outputs are captured as artifacts
- failed code produces a repairable run log instead of breaking the app
- README and UI copy do not require Docker as the normal path

## Phase 5: Controlled Visualization

Recommendation: treat visualization as a governed system, not as free-form model creativity.

Add chart rules:

- time trend -> line chart
- category comparison -> bar chart
- part-to-whole with few categories -> pie or stacked bar
- distribution -> histogram or box plot
- relationship -> scatter
- KPI summary -> metric card
- detailed evidence -> table

Add visual contracts:

- title
- subtitle or takeaway
- metric definition
- source table
- units
- caveats
- chart type
- dimensions and measures

Done when:

- the same analytical intent produces stable chart types
- chart artifacts are rendered from structured specs
- the UI can preview chart/table/dashboard artifacts consistently

## Phase 6: Report Templates

Recommendation: standardize report output early, because this directly solves the current Markdown randomness problem.

Add templates:

- KPI report
- metric diagnostics report
- product/business analysis report
- executive summary
- dashboard summary

Each report should enforce:

- answer-first summary
- evidence section
- charts/tables
- caveats
- source metadata
- reproducibility appendix

Done when:

- Markdown reports follow predictable structure
- HTML export is generated from the same structured report
- report format can be selected or configured

## Phase 7: Dashboard Artifact

Recommendation: build a lightweight dashboard artifact before attempting a full BI system.

Add dashboard spec:

- metric cards
- charts
- tables
- filters
- source notes
- caveats

Done when:

- a run can produce a dashboard artifact
- the UI renders it as a workbench artifact
- dashboard structure is generated from a schema, not free-form HTML

## Phase 7.5: Validation Gate

Recommendation: make quality control mandatory before a run is marked complete.

Add a pre-delivery validation gate:

- every key claim maps to evidence
- tables and charts have source metadata
- report blocks satisfy the structured schema
- chart types follow chart rules
- missing context, data quality issues, and metric ambiguity are surfaced
- artifacts can render or expose a useful fallback

Done when:

- failed validation creates a visible run-log entry and warning artifact
- the UI distinguishes completed, completed-with-warnings, and failed validation states
- reports cannot be silently marked complete when major evidence or artifact checks fail

## Phase 8: External API Data Sources

Recommendation: add this after local files and context are stable.

Add connector basics:

- API name
- base URL
- auth config
- request templates
- response schema
- cached snapshots

Done when:

- the user can configure an external API source
- a run can fetch data into a snapshot
- the snapshot is treated like a normal dataset

## Phase 9: Real-Use Refinement

Recommendation: start using the tool with real analysis work before overbuilding.

Refine based on actual runs:

- which skills are missing
- which report templates are useful
- which chart rules need overrides
- what each project context should remember
- what artifact types matter most
- where the UI feels slow or unclear

Done when:

- repeated real workflows require less manual prompting than ChatGPT web
- outputs are more stable and presentable
- project context and visualization rules meaningfully reduce repeated work

## Immediate Next Recommendation

Next implementation step:

1. Add analysis project CRUD and project-scoped context CRUD in the UI and backend.
2. Add structured report template contracts.
3. Add a first LLM planner that reads skill + context + dataset profile and emits a constrained analysis plan.

This keeps the project aligned with the central goal: reproduce the Codex/Data Analytics-style thinking first, then gradually polish through real usage.
