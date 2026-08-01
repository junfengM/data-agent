Name: Metric Diagnostics
Use When: The user asks why a metric changed, dropped, increased, or differs from a baseline.

# Metric Diagnostics

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. Identify metric definition, time window, baseline, population, and filters.
2. Reproduce the metric before explaining it.
3. Compare current period against baseline.
4. Segment by likely drivers.
5. Quantify contribution where possible.
6. Separate validated drivers from hypotheses.
7. Recommend follow-up checks.

## Measurement Calibration

Before diagnosing metric movement, reproduce and validate the metric independently. Do not explain a metric until you have confirmed the number yourself.

Measurement errors (wrong window, stale data, filter mismatch) are the most common cause of false diagnostic conclusions. Spend the time to calibrate before decomposing. If the metric cannot be reproduced, the entire diagnostic is invalid.

1. Re-run the metric query against the source data. Use the same time window, population definition, and filter set. If the metric is pre-computed in a dashboard or report, trace it back to the underlying query or event-level data.
2. Check for measurement artifacts:
   - Incomplete data: partial periods, late-arriving events, backfill gaps.
   - Sampling changes: has the sampling rate or methodology changed between periods?
   - Filter drift: do filters applied today match those used at baseline?
   - Caching: is the metric sourced from a stale cache or pre-aggregated table?
3. Verify against a known reference: prior-period self-consistency (does the same query reproduce the baseline correctly?), cross-table reconciliation, or a proxy metric that should move in parallel.
4. If reproduction fails or the metric cannot be validated within acceptable tolerance (<1%), flag it as unverified. Downgrade all downstream conclusions. Do not proceed with driver analysis on an unverified metric.
5. Record the calibration result: source table, query timestamp, row count, metric value, and any discrepancy vs the user-quoted value. This becomes the Metric reproduction table in the output.

## Driver Decomposition Framework

Decompose the total change into attributable components. The goal is to explain the full change, not just find one plausible cause.

Use additive decomposition: each component's contribution should sum toward the total change. If components overlap (e.g., a category shift that also reflects a seasonal pattern), isolate the independent contribution of each and note the overlap explicitly. A driver is not useful unless its contribution can be separated from the others.

1. **Segment contribution**: Compute the metric per segment (category, channel, region, cohort) for current and baseline periods. Calculate each segment's absolute contribution: (current_value - baseline_value) per segment. Rank by absolute contribution. A segment can be a net detractor even if its own metric improved, if its population share shrank enough.
2. **Mix shift**: Check whether the segment composition changed between periods. A flat aggregate can mask offsetting shifts within segments. Compute each segment's share of the total population in both periods. Flag segments whose share changed by >2 percentage points.
3. **Seasonality**: Compare against the same period in the prior cycle (year-over-year), not the immediately preceding period. Adjacent-period comparisons confuse trend with seasonal variation. For weekly patterns use same-day-of-week from prior weeks; for intra-day use same-hour from prior days.
4. **Outliers**: Identify individual observations or dates that disproportionately influence the aggregate. Remove top and bottom 1% and recalculate to measure outlier sensitivity. Flag dates with values >3 standard deviations from the period mean.
5. **Recency vs accumulation**: Determine whether the change is driven by recent data points or gradual accumulation across the full window. Plot a running cumulative metric to distinguish. A sharp inflection near period-end suggests a recent event; a smooth divergence suggests a sustained shift.

Stop decomposing when: (a) all remaining unexplained variance is below 5% of total change, (b) the next decomposition dimension requires data not available, or (c) further segmentation produces segments too small for statistical reliability (<30 observations). State the stopping reason in the output so the reader knows the diagnostic boundary.

A practical limit is 3-5 drivers. Beyond that, the diagnostic becomes noise. If you have more than 5 candidates, consolidate or raise the contribution threshold to focus on what matters.

## Diagnostic Plan Selection

Choose the diagnostic approach based on the question type and data structure. Pick one plan as primary; others may supplement.

1. **Single-metric drill-down**: For "why did X change?", segment the metric by the 3-5 dimensions most likely to explain variance (category, channel, geography, customer segment). Compute contribution per segment, order by absolute contribution. Works best when the metric has clear segmentation dimensions in the data.
2. **Comparative segment analysis**: For "why is segment A different from segment B?", normalize by segment size, then compare sub-segment distributions within each population. Look for structural differences in the underlying mix rather than level differences.
3. **Time-series decomposition**: For trend or seasonal questions, decompose into trend, seasonal, and residual components using moving averages or STL. Check whether the residual is within expected noise. Use when the question involves time patterns rather than point-in-time comparison.
4. **Before-after analysis**: For known intervention points (campaign launch, policy change, site update), use a short symmetrical window before and after the event. Control for unrelated concurrent changes by comparing against a holdout population that did not receive the intervention.

Default to single-metric drill-down when the question is ambiguous. Note the assumption explicitly in the output.

## Certainty Labeling

Every driver must carry a certainty label. Do not present hypotheses as findings.

Certainty labeling is the difference between a diagnostic and a guess. If the user acts on a hypothesis labeled as a finding, they will waste time and lose trust. Err toward lower certainty when the data is incomplete or the metric cannot be fully decomposed.

1. **Validated**: Contribution measured, quantified, and confirmed through direct segmentation or regression. Direction and magnitude are both established. A driver reaches validated only when its segment-level computation independently reproduces the contribution.
2. **Likely**: Direction confirmed (segment moves as expected and timing aligns) but magnitude not fully isolated. Common causes: overlap with other drivers, data granularity limits, or identification through correlation rather than direct segmentation.
3. **Hypothesis**: Plausible explanation consistent with the data pattern but insufficient evidence to confirm. Must be explicitly labeled as unresolved with a note on what additional data or analysis would confirm or refute it.
4. **Ruled out**: Suspected drivers that were tested and found not to explain the change. Include to prevent circling back and to demonstrate diagnostic thoroughness.

A driver below 5% absolute contribution should not be labeled validated unless its cumulative effect with closely related drivers is material (>10% combined).

## Quality Bar

The diagnostic is not complete until these conditions are met. If a condition cannot be met, document why and adjust certainty downward across all conclusions.

1. Metric definition confirmed: time window, population, aggregation method, and filter set all match the user's question.
2. Metric value independently reproduced with <1% discrepancy from the user-quoted or dashboard value.
3. At least one driver is quantified with contribution percentage and labeled validated or likely.
4. Measurement artifacts checked: sampling bias, data freshness gap, filter definition drift, and traffic filtering differences. Each ruled out or explicitly flagged.
5. All unresolved drivers are explicitly labeled as hypotheses with concrete next steps to validate (e.g., "pull channel-level data for period X", "check conversion rate by device").
6. Total explained contribution (sum of validated + likely) accounts for ≥70% of the observed change. If not, state the unexplained gap and suggest where remaining variance may reside.

Before delivering, review the full diagnostic against this checklist. If any item fails, go back and address it or document the failure explicitly in caveats. A delivered diagnostic that skips calibration or mislabels hypotheses as findings is worse than no diagnostic at all.

## Output Contract

Every diagnostic response must include these elements in this order. Omitted elements require an explicit note explaining why.

1. **Short answer** (2-4 sentences): What changed, by how much, the primary driver, and the certainty level. Lead with the conclusion — do not narrate the discovery process. A good short answer names the metric, states the change direction and magnitude, identifies the top driver with its contribution percent, and gives the certainty label. Example: "Revenue dropped 12% ($240K) period-over-period, driven primarily by a 40% decline in Channel A (8pp contribution, validated). Two additional hypotheses remain unresolved."
2. **Metric reproduction table**: Columns for source table, query timestamp, row count, metric value (current period), metric value (baseline period), absolute change, percent change. Include a discrepancy note row if the user-provided value differs from reproduction by >1%.
3. **Driver contribution table**: Ranked table with columns for rank, driver name, certainty label (validated/likely/hypothesis), absolute contribution, percent contribution, cumulative percent. Validated drivers first, then likely, then hypotheses. Include a totals row. Hypothesis contributions in brackets to signal unconfirmed.
4. **Supporting charts**: At minimum, a time-series of the metric with baseline period marked, and a waterfall chart showing driver contributions from baseline to current. Additional per plan: segment breakdown bar chart (drill-down), trend-vs-seasonal overlay (time-series), before-after comparison (intervention).
5. **Caveats and unresolved hypotheses**: Bullet list of all labeled hypotheses with validation steps, measurement artifacts flagged during calibration, and the unexplained gap if total explained is below 70%. Follow-up checks as a separate bullet group with specific actions.

## Skill Dependencies

- `$chart-rules`: Auto-loaded when generating driver charts
- `$visualize-data`: Load for chart design and QA of driver visualizations
- `$build-report`: Auto-loaded in report mode

## Available Tools

- `preflight.py`：项目预检信封
- `validation.py`：验证门——证据覆盖、源安全
- `execution.py`：本地 Python 代码执行
