Name: Skill Router
Use When: The user asks a data analysis question and the harness needs to select the right workflow.

# Skill Router

Route the request to the narrowest skill that can produce a useful, evidence-backed result.

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Run project preflight to load project context, semantic layer, and source-routing preferences
2. Apply semantic-layer lookup when request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Routing Protocol

### 1. Determine Response Mode

Choose the output format based on user intent:

- `inline`: Quick answer, single table/chart, no report structure needed
- `report`: Polished analytical report with narrative flow (default)
- `dashboard`: Reusable monitoring or exploration surface
- `notebook`: Exploratory analysis with code visibility

### 2. Select Primary Skill

Route to the smallest useful skill:

- `$metric-diagnostics`: Why a metric moved, regressed, improved, or differs from expectation
- `$kpi-reporting`: Recurring performance updates, scorecards, WBR, MBR, QBR, target pacing
- `$product-analysis`: Data-backed recommendation or product/business decision (default for open-ended)
- `$explore-data`: Open-ended insight discovery from row-level data — find what stands out when no specific question or decision frame is provided
- `$visualize-data`: Chart design, chart QA, or visual explanation
- `$build-report`: Polished analytical report
- `$build-dashboard`: Reusable monitoring or exploration surface
- `$validate-data`: Pre-delivery QA — validate methodology, calculations, conclusions before handoff
- `$analyze-data-quality`: Source trust assessment — freshness, grain, completeness, outliers
- `$gather-business-context`: Gather business context when project context is thin or missing
- `$design-kpis`: KPI framework design — define metrics, set targets, create measurement plans
- `$market-sizing`: TAM/SAM/SOM, opportunity sizing with sensitivity analysis
- `$jupyter-notebooks`: Reproducible analysis notebooks for audit trails and exploratory work

**Routing note — open-ended questions:** When the user provides detailed data but no specific question or decision frame, route to `$explore-data` instead of `$product-analysis`. Use `$product-analysis` only when a business decision or recommendation is explicitly requested. If uncertain, prefer `$explore-data` for data-first exploration and escalate to `$product-analysis` if findings reveal a clear decision need.

### 3. Load Auxiliary Skills

Automatically load dependencies:

- `$chart-rules`: Load when primary skill may generate charts ($product-analysis, $metric-diagnostics, $kpi-reporting, $visualize-data, $build-dashboard, $build-report, $explore-data)
- `$user-context`: Mandatory pre-answer gate before every analysis run
- `$gather-business-context`: Load when project context is thin or user switches product area
- `$analyze-data-quality`: Load when source data trustworthiness is uncertain. Also load before ranking insights in `$explore-data`.
- `$validate-data`: Load before stakeholder-facing delivery
- `$design-kpis`: Load when metrics need definition before analysis can proceed
- `$market-sizing`: Load when sizing opportunity or market scope
- `$jupyter-notebooks`: Load when reproducible notebook output is needed

### 4. Apply Semantic Layer

Before analysis, check for:

- Canonical metric definitions in project context
- Dimension and grain specifications
- Source table/file precedence
- Known data issues and caveats

If semantic layer exists, use it as starting map for candidate metrics, tables, joins, filters, caveats, source precedence.

### 5. Source Discovery And Verification

Do not stop at semantic layer or first plausible source:

1. Search across available sources (datasets, project context, semantic layer)
2. For source-backed analytical work, verify through live data reads
3. Use combined evidence to determine which source controls the answer
4. Note meaningful disagreements and state why selected source is authoritative

### 6. Source Access Guardrail

Before querying sources, building artifacts, or drawing conclusions:

- If required source is unavailable, stop that path
- Tell user what source is needed, ask them to make it available
- Do not treat weaker substitutes as equivalent
- If missing source is only optional enrichment, continue with strongest available evidence and label the gap

### 7. Run Project Preflight

Load `$user-context` and build compact envelope:

- Selected project and project contexts
- Semantic layer definitions
- Dataset profiles and schema summaries
- Missing definitions or context gaps
- Source and validation obligations
- Source-routing preferences

### 8. Execute Analysis

Follow skill-specific workflow:

1. Profile datasets (deterministic)
2. Generate analysis plan (LLM)
3. Execute code steps (controlled runner)
4. Synthesize report (LLM)

### 9. Apply Validation Gates

Before delivery, verify:

- Every key claim maps to table/chart evidence
- Tables/charts have source metadata
- Report blocks satisfy schema
- Chart types follow chart-rules
- Missing context and data quality issues are surfaced
- Generated artifacts can render or expose useful fallback

### 10. Completion Gates

Report completion:

- Report run must choose exactly one report delivery mode
- Do not end with only inline/chat summary
- If required deliverable is skipped, include explicit omission reason
- Verify generated artifacts by opening, reading, rendering, or inspecting them
- Check source-backed claims against controlling sources
- Call out unresolved gaps or caveats when they materially affect conclusion

## Quality Bar

- Prefer deterministic tool output over unsupported narrative.
- Preserve data sources, code, queries, assumptions, caveats, and run logs.
- Separate facts, inferences, and recommendations.
- Bound open-ended exploration with candidate angles and scoring.
- Do not compute final numbers from memory or prose.
- Do not invent metric definitions.
- Do not assume global business background.

## Run Log Contract

Each run should expose in the run log:

- Response mode: inline/report/dashboard/notebook
- Primary skill selected and reason
- Auxiliary skills loaded and reason
- Semantic layer items used
- Source discovery results
- Source access guardrail decisions
- Required tools and their outputs
- Expected artifact types
- Validation gate results
- Completion gate status
