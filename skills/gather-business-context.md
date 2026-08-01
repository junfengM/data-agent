Name: Gather Business Context
Use When: Project context is thin or missing, user switches to a new product area, or the analysis question is open-ended and needs bounding.

# Gather Business Context

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## When To Load

- Load when project context is thin or missing — no business background, no metric definitions, no audience notes, no prior analysis record.
- Load when the user switches to a new product area not covered by existing context files or semantic layer entries.
- Load when the analysis question is open-ended ("analyze the business", "what should we focus on?") and needs bounding before data work begins.
- Load when prior analysis output referenced unfamiliar terms, metrics, or assumptions that were never documented.
- Do NOT load for simple metric lookups, single-chart requests, or data quality checks where context is already sufficient.

## Workflow

1. **Load existing project context.**
   Read what the project already knows from config files, semantic layer, and prior context documents. List every context item found: business background, metric definitions, reporting preferences, known data issues, audience notes, source routing preferences.
   Do not assume anything is present — verify by reading files. If the preflight envelope from `$user-context` returned context, start from there. Do not re-read files the preflight already loaded.

2. **Identify context gaps.**
   Compare what exists against the categories in steps 3–7 below. For each missing or incomplete category, assign severity:
   - **Blocker**: Cannot produce reliable analysis without this context.
   - **Caution**: Analysis can proceed but confidence will be reduced; must flag in output.
   - **Nice-to-have**: Adds depth or color but does not change conclusions.
   Record gaps in a simple table: category, what is missing, severity, impact if left unfilled.

3. **Gather business background.**
   Determine: product or business area under analysis, business model and revenue drivers, current priorities and initiatives, key decisions pending, recent changes or events that may affect the data being analyzed.
   If context is missing, derive reasonable assumptions from available data patterns and explicitly label them as assumptions. For example: "No revenue data available — assuming e-commerce transaction model based on payment columns found in orders table."
   Check whether the business area has a semantic layer entry. If it does, use it as the starting point. If it does not, note the gap.

4. **Gather stakeholder context.**
   Identify: who is the intended audience? what specific decision will this analysis inform? what format, depth, and cadence do they prefer?
   When the audience is unknown, default to "general analyst audience" and note the assumption. Tailor output depth and language to the audience once identified.
   Map audience type to output expectations: executive (answer-first, 1-page), product lead (options with trade-offs, 3-5 pages), operational owner (detailed breakdowns, drillable), analyst peer (methodology-visible, reproducible).

5. **Gather metric context.**
   Collect from semantic layer and project config: canonical metric names and definitions, calculation formulas, business targets or thresholds, comparison baselines, known data issues or caveats per metric.
   Flag where definitions are missing, ambiguous, or conflict across sources. Do not invent definitions — mark them as missing and state the derivation if one is improvised.
   For each metric found, record: name, definition source (file:line), formula if available, target if applicable, known caveats.

6. **Gather source context.**
   Map available data sources: which tables, files, or APIs are available to the project? which are authoritative for which metrics? what are their known limitations — freshness, completeness, schema quirks, join compatibility?
   Note trust ratings from prior `$analyze-data-quality` runs. Respect source routing preferences from `$user-context`. If no trust rating exists for a critical source, flag it as a caution gap.
   For each source, record: name, path, type, freshness, trust rating (if known), authoritative-for list, known limitations.

7. **Gather prior analysis context.**
   Review: what has been analyzed before in this project area? what conclusions were reached? what was left unresolved or recommended as follow-up? what artifacts exist (reports, dashboards, notebooks) and where are they?
   Check project run history and artifact directories. Look for analysis runs tagged with the same product area or metrics.
   Avoid re-running analysis that has already been done. If prior conclusions are still valid, reference them. If they are stale, note the staleness and what has changed.

8. **Structure context into compact output.**
   Organize findings by the categories in steps 3–7. For each category, list: what is known (with source), what is missing (with severity), and what reference files back each claim.
   Keep the output scannable — the next skill using this context should find answers in seconds. Prefer bullet lists over paragraphs.
   Use a consistent template: category heading, "Known" sub-section, "Gaps" sub-section, "References" sub-section. This template lets downstream skills jump directly to the section they need.

## Output Contract

- **Context summary** — structured by category: business background, stakeholders, metrics, sources, prior analysis. Each category lists what is known, how it was sourced, and confidence level.
- **Context gaps identified** — each gap listed with category, severity (blocker / caution / nice-to-have), and specific impact on analysis. Blockers must be resolved before proceeding; cautions must be surfaced in all downstream output.
- **Recommended actions** — what context to gather before deep analysis, ordered by priority. Each action names the gap it fills and the expected improvement in analysis quality.
- **Key questions to ask stakeholders** — concrete, answerable questions that fill the highest-impact gaps. Each question states what category it addresses and why the answer matters. Avoid open-ended surveys — prefer specific, falsifiable questions.
- **Source-of-truth references** — which files, config keys, or artifacts are authoritative for each context category. Use specific paths and line references, not vague category names.

## Skill Dependencies

- `$user-context`: Already loaded via pre-answer gate. Use for semantic layer lookup, source routing preferences, and existing project context.
- `$analyze-data-quality`: If source trust ratings are unavailable or stale, load to assess data quality before relying on sources for context decisions.

## Integration Notes

- This skill is a **precursor** to analysis skills (`$product-analysis`, `$metric-diagnostics`, `$kpi-reporting`). It should run before them when context is insufficient, not instead of them.
- Output from this skill feeds directly into the analysis plan of the primary skill. Structure the output so the primary skill's workflow step 1 ("Load project context") is satisfied without re-reading everything.
- If `$user-context` preflight already returned a complete context envelope, skip this skill. It exists for cases where preflight alone is not enough.
- This skill does NOT produce analytical output itself — no charts, no metric calculations, no reports. It produces structured context that makes analysis output better.

## Behavior Principles

- Do not ask stakeholders for context that can be inferred from available data. Derive what you can, label assumptions, and only escalate gaps that are blockers.
- Do not treat missing context as a stop condition. Produce the best analysis possible with available information and surface what is unknown.
- Do not overload the output. The next skill using this context needs to find answers in seconds — prefer density over completeness.
- Do not store gathered context as a new permanent file unless the user explicitly requests it. Context gathered here feeds the current analysis run.
- When the same information appears in multiple sources, state which source is authoritative and why. Disagreements between sources are a finding, not a bug to silently resolve.

## Quality Bar

Before signing off, confirm:

1. All 8 workflow steps have been addressed, even if the answer is "unknown" or "not applicable."
2. Context gaps are categorized by severity and each gap has a stated impact on analysis quality.
3. Assumptions are explicitly labeled as assumptions, not stated as facts.
4. Source-of-truth references include specific file paths or config keys — not vague category names like "project docs."
5. Stakeholder questions are concrete and answerable — each has a clear purpose tied to a specific gap.
6. The output template (Known / Gaps / References) is followed for each category so downstream skills can scan quickly.

## Available Tools

- `preflight.py`：项目预检信封，加载项目上下文和语义层
