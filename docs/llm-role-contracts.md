# LLM Role Contracts

The Data Agent uses five LLM roles. Each has a bounded contract: what it can decide, what tools it can call, and what output it must produce. No role may exceed its contract.

## Router

**Responsibility**: Choose primary and auxiliary skills for the current question.

**Contract**:
- Read `skills/index.md` routing rules
- Select exactly one primary skill
- Load required auxiliary skills per dependency rules
- Output skill chain with rationale
- Do NOT begin analysis — hand off to Planner

**Output**: `{primary_skill: str, auxiliary_skills: list[str], rationale: str}`

## Planner

**Responsibility**: Create a bounded analysis plan with candidate angles.

**Contract**:
- Read project context, semantic layer, dataset profiles
- Generate 3-5 candidate analysis angles, each scored on 6 dimensions (impact, confidence, actionability, novelty, relevance, data sufficiency)
- Select top 2-3 angles for deep-dive
- Produce executable code steps with clear inputs/outputs
- Include explicit caveats and data limitations
- Output structured JSON plan

**Output**: `{plan_steps: list, candidate_angles: list, caveats: list, selected_skills: list}`

## Analyst

**Responsibility**: Execute code steps deterministically and collect evidence.

**Contract**:
- Call deterministic tools only (execution.py, preflight.py)
- Do NOT compute final numbers from memory or prose
- Do NOT invent metric definitions
- Capture all stdout/stderr, generated tables, and charts
- Record source provenance for every table and chart
- Return structured step results with evidence

**Output**: `step_results: list[{tables, charts, stdout, stderr, code, description}]`

## Critic / Validator

**Responsibility**: Verify evidence, caveats, source safety before delivery.

**Contract**:
- Run all validation gates (evidence coverage, source metadata, schema compliance, chart contracts, context caveats, renderability, source safety, sensitive payload)
- Map validation results to run status (pass → completed, warnings → completed_with_warnings, failures → failed)
- Never suppress validation failures
- Surface caveats, data quality issues, and missing context
- Output validation results with gate-level severity

**Output**: `list[ValidationResult]` with severity pass/warning/fail

## Reporter

**Responsibility**: Synthesize evidence into a decision-oriented report.

**Contract**:
- Write answer-first narrative (conclusion → evidence → caveats → next steps)
- Every key claim must reference evidence ids (chart_id, table_id)
- Include source metadata and caveats
- Structure report as blocks: heading, prose, table, chart, metric_card, callout, source_note
- Do NOT introduce unsupported claims
- Output structured report markdown

**Output**: `{report_md: str, title: str, summary: str, evidence_ids: list, caveats: list}`

## Cross-Role Rules

1. Router hands off to Planner. Planner hands off to Analyst. Analyst hands off to Critic. Critic hands off to Reporter.
2. No role may skip validation gates before Reporter runs.
3. Tool calls are tracked per-step and appear in the run log.
4. LLM may be reused across roles via a single conversation, but role boundaries must be explicit in the prompt.
5. Each role's output becomes the next role's input — no hidden state.
