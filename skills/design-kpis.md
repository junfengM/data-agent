Name: Design KPIs
Use When: The user needs to define a KPI framework, design metrics, set targets, or create a measurement plan.

# Design KPIs

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. **Clarify the business goal.** Start with the decision the KPI framework should inform, not the symptom.
   - If the user says "revenue is down," ask: "what action would you take if you knew the answer?"
   - If the user cannot name a decision the framework would drive, pause and narrow scope before designing metrics.
   - Record the goal in one sentence. Reject multi-goal frameworks without explicit prioritization.
   - Good goal: "Decide which product category to invest marketing spend in next quarter."
   - Bad goal: "Understand our business better." A framework optimized for everything is optimized for nothing.

2. **Identify the primary KPI.** Select the single metric that best captures success against the stated goal.
   - A primary KPI must be actionable (the team can move it through decisions), attributable (you can trace changes to interventions), and timely (it moves on a cadence the business can respond to).
   - Reject composite indices as primary KPIs — they average away signal.
   - If the user proposes a ratio (e.g., "revenue per user"), decompose it: which component drives the decision — numerator, denominator, or both?
   - Name the KPI, state its formula, and confirm the user agrees this is the number they would manage to.

3. **Define driver metrics.** Derive 2–5 leading indicators that influence the primary KPI.
   - For each driver, state a testable hypothesis with direction and approximate magnitude: "if X improves by Y%, the primary KPI should improve by approximately Z%."
   - Prefer drivers the business can directly control (pricing, inventory, staffing, channel mix) over exogenous factors (weather, macro trends, competitor actions).
   - When causal direction is uncertain — does higher engagement drive revenue, or does revenue growth attract more engaged users? — label the relationship as associative.
   - For associative drivers, note what experiment or additional data would confirm causality.
   - A driver without a testable hypothesis is not a driver; it is trivia. Remove it.

4. **Define guardrail metrics.** Identify metrics that must not degrade while optimizing the primary KPI.
   - Guardrails must cover three dimensions:
     - Data quality: is the primary KPI still reliably measured, or is metric movement a measurement artifact?
     - User experience: is the customer harmed? Check churn, NPS, support ticket volume, time-to-resolution.
     - Business risk: is margin compressing? Are compliance thresholds breached? Is retention eroding?
   - Each guardrail needs a specific floor or ceiling threshold — not "monitor X" but "churn must stay below 5% monthly."
   - If the user omits a dimension, flag the gap explicitly. The most common failure: shipping a revenue win that destroys retention.

5. **Set targets.** For each metric, establish a baseline by querying actual historical data.
   - Never accept the user's intuition or a dashboard screenshot as baseline. Query the source directly.
   - Report: baseline value, lookback period, number of observations, and any seasonality adjustments applied.
   - Propose a target with explicit rationale category: trend extrapolation (linear projection from last N periods), industry benchmark (cite source), or internal goal (cite who set it and when).
   - Specify both the time horizon ("by Q3 2026") and the measurement period ("evaluated as 4-week rolling average to smooth weekly noise").
   - Targets without a queried baseline are guesses. Label them as ungrounded.

6. **Design the measurement plan.** For each metric, document the full execution path.
   - Specify: source table or file path, calculation formula (SQL or readable pseudocode), refresh cadence (daily/weekly/monthly), grain (per transaction, per user-day, per store-week), and aggregation method (sum, average, median, percentile).
   - For multi-source metrics: list join keys and verify join compatibility against `$analyze-data-quality`.
   - Prefer simple, auditable formulas. A metric that fits in one SQL `SELECT` is maintainable; one requiring a multi-step pipeline with 5 intermediate tables is fragile — justify it.
   - Flag any metric whose calculation cannot be expressed in a single query and explain why.

7. **Validate data availability.** Load `$analyze-data-quality` and verify each source.
   - For every metric, report: source file or table exists (yes/no), last refresh date, completeness score (null rate), freshness gap vs. required cadence, and population coverage.
   - Reject any metric whose source fails the "Use with caution" trust threshold.
   - Metrics without validated sources are downgraded to aspirational and labeled clearly in all output tables.
   - When a source is unavailable, do not silently substitute a proxy — flag it and ask the user to provide the data.

8. **Document definitions in semantic-layer format.** Produce YAML entries ready for `config/semantic-layer.yaml`.
   - Each entry must include: metric name, formula, grain, source table, dimensions for segmentation, known caveats, and last validation date.
   - Use the format from `$user-context` semantic-layer registry.
   - Before writing, check whether the existing semantic layer already defines a metric with the same name or intent. If it does, reconcile — update the existing entry rather than creating a duplicate.
   - If definitions conflict, flag the discrepancy and let the user resolve it.

9. **Test framework completeness.** Apply three test questions before signing off.
   - "If I look at this framework each review period, can I answer 'are we winning?' in 5 seconds?" The primary KPI alone should answer this.
   - "If the primary KPI moved 10% in either direction, do the drivers explain why?" Every driver should trace back to the primary.
   - "If I optimized only the primary KPI for 3 months, would a guardrail catch the damage?" At least one guardrail should fire before irreversible harm.
   - If any test fails, close the gap before signing off.

## Output Contract

- **KPI framework summary** — one table listing the primary KPI, each driver metric, and each guardrail metric. Columns: metric name, type (primary/driver/guardrail), formula, current baseline, target, threshold (for guardrails), and data availability status (validated/aspirational).
- **Metric definitions** — for each metric: name, formula, grain, source table, refresh cadence, aggregation method, segmentation dimensions, and data availability status.
- **Target rationale** — per-target record with: baseline value and source query, proposed target, rationale category (trend extrapolation / industry benchmark / internal goal), time horizon, and measurement period.
- **Measurement plan** — per-metric execution table: data sources, join keys (if multi-source), calculation SQL or pseudocode, refresh cadence, and owner (if known).
- **Semantic-layer entries** — YAML blocks ready for insertion into `config/semantic-layer.yaml`, one per metric, following the `$user-context` registry format. Include last-validation timestamp.
- **Risks and caveats** — data quality issues per source, definitional edge cases (e.g., how to count users who churn mid-period), missing guardrail dimensions, metrics downgraded to aspirational, unresolved causal-direction hypotheses, and source staleness warnings.

## Skill Dependencies

- `$analyze-data-quality`: Check source data fitness before committing to metrics that depend on it. Load during step 7.
- `$chart-rules`: For visualizing KPI hierarchies (driver tree diagrams) and target-vs-actual comparisons (waterfall charts, bullet graphs).

## Quality Bar

Before signing off, confirm:

1. Primary KPI is a single, unambiguous, actionable metric — not a composite index, not a ratio hiding numerator/denominator trade-offs. It passes the "5-second answer" test: can someone glance at this number and know whether to celebrate or intervene?
2. Each driver metric carries a stated hypothesis with direction and approximate magnitude. Hypotheses without evidence are explicitly labeled associative. No driver is included just because "it seems related."
3. Guardrails cover data quality, user experience, and business risk. Missing dimensions are explicitly flagged — never silently omitted. Every guardrail has a numeric threshold, not a vague "watch this" instruction.
4. Every metric has a defined formula, grain, source table, and refresh cadence. No placeholders like "TBD" or "figure it out later." Metrics that cannot be fully specified are downgraded to aspirational.
5. All targets are time-bound and grounded in baseline data queried from actual sources. The baseline query is included in the output. Targets set without a queried baseline are labeled ungrounded.
6. The measurement plan is executable with available data sources. Metrics whose sources are missing or fail quality checks are downgraded to aspirational and labeled in all output tables and the framework summary.

## Available Tools

- `preflight.py`：项目预检信封
- `chart_contract.py`：图表类型验证
