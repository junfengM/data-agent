Name: Product Analysis
Use When: The user needs data-backed evidence to choose a direction, prioritize an opportunity, or understand business/product implications.

# Product Analysis

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. Clarify the decision, population, time window, and success metric when missing.
2. Inspect available datasets and schema.
3. Generate an analysis plan with expected tables and charts.
4. Execute deterministic Python or SQL.
5. Validate data quality and sample size.
6. Summarize findings answer-first.
7. State caveats, alternatives, and next checks.

## Decision Framing

Before generating angles or pulling data, frame the decision:

1. **What is being decided?** Single choice, prioritization among options, or go/no-go.
2. **Who decides?** Executive, product lead, operational owner. Tailor depth and format to that audience.
3. **What evidence would change the answer?** State the falsifiable condition upfront. If no data could change the decision, surface that and stop.
4. **What is the cost of being wrong?** Size the risk. High-stakes decisions demand higher confidence and explicit sensitivity checks.
5. **Time horizon.** Point-in-time snapshot vs. trend that must hold for N months.

If these five cannot be answered, push back. Without a decision frame it's exploration, not product analysis.

## Evidence Translation Lenses

Raw metrics carry no meaning without the business translation. Apply at least one lens per finding:

**Strategic lens (revenue / market)**
- Revenue impact: absolute $, margin percentage, customer lifetime value shift
- Market position: share change, competitive win/loss rates
- Pricing sensitivity: elasticity estimates, willingness-to-pay signals

**Product lens (adoption / retention)**
- Adoption velocity: time-to-first-value, activation rate, feature discovery
- Engagement depth: DAU/MAU, session frequency, feature usage breadth
- Retention: cohort curves, churn by segment, resurrection rate

**Operational lens (efficiency / cost)**
- Unit economics: cost per acquisition, cost per serve, support ticket rate
- Throughput: time-to-complete, automation rate, error and redo rate
- Scalability: marginal cost curves, capacity utilization
Pick the lens that matches the decision type. A strategic decision showing only engagement metrics is under-scoped; a product decision missing retention data is incomplete.

## Candidate Angle Generation

Generate candidate angles systematically. Do not hunt randomly through data:
1. **Time trends.** Plot the metric over the decision window. Look for inflections, seasonality, acceleration or deceleration.
2. **Category comparisons.** Break the metric by category (product line, channel, region). Rank by contribution share.
3. **Segment differences.** Split by user segment (new vs. returning, tier, behavior cluster). Test for meaningful gaps.
4. **Funnel and conversion.** Map user journey stages. Find the step with the largest drop-off or the highest leverage.
5. **Cohort analysis.** Group users by acquisition period. Compare retention or behavior curves across cohorts.
6. **Correlation checks.** Test relationships between candidate drivers and the outcome metric. Flag potential confounders.
7. **Top and bottom rankings.** Identify top-N and bottom-N performers. Profile what separates them.

Not all angles apply to every question. Select 2-4 that fit the decision frame, generate findings, then score them against the rubric.
## Scoring Rubric

Score each candidate angle on these dimensions (scale 1-5). Only advance angles that clear the composite bar:

| Dimension | What it measures |
|-----------|-----------------|
| **Impact size** | How large is the effect on the decision metric? |
| **Confidence** | How robust is the signal? Check sample size, variance, stability across time splits. |
| **Actionability** | Can the decision-maker act on this finding directly? |
| **Novelty** | Does this reveal something not already known? Avoid re-stating the obvious. |
| **Relevance** | Does this answer the framed decision? Off-topic findings waste time. |
| **Data sufficiency** | Is the underlying data complete and clean enough to support the claim? |

Threshold rules:
- An angle scoring below 3 on impact, confidence, or actionability should not appear in the recommendation.
- An angle scoring below 3 on data sufficiency must carry an explicit caveat in output.
- Score before writing the recommendation. Discard weak angles; do not list them just to fill space.

## Depth Gate

Analysis must pass through three gates in order. Do not skip levels:

**Gate 1 — Surface-level findings (must complete)**
- What happened: direction, magnitude, time window. One-paragraph summary backed by a reproducible query or chart.
- Complete this gate before moving on.

**Gate 2 — Validated findings (must complete before recommendation)**
- Why did it happen? Driver decomposition with contribution quantification.
- At least two angles tested, one segmentation cut. Cross-checked against a second data cut or hold-out period.
- Failed validation is itself a finding — state what was tested and why it didn't hold.

**Gate 3 — Scored recommendations (deliverable)**
- Ranked actions with impact estimates, confidence, and trade-offs. Each tied to a Gate 2 finding.
- Include: what to do, expected effect, confidence, timeline, failure signals to watch.

Gate 1 alone is a status update, not product analysis. Push to Gate 2 at minimum. Gate 3 is the target for completed delivery.

## Quality Bar

Before handing off, verify all seven checks. If any check fails, fix before delivery:

1. **Decision frame is stated.** The reader knows what is being decided and why it matters.
2. **Pre-answer gate was run.** `$user-context` loaded, preflight complete, sources verified.
3. **At least two angles tested.** Single-angle analysis is fragile and easily misleading.
4. **Drivers are quantified.** "X drove 22% of the decline" not "X seems correlated with the drop."
5. **Caveats are specific.** "Sample limited to Q1-Q3 2025, N=1,240; seasonal effects not controlled" not "data may be incomplete."
6. **Alternative explanations listed.** What else could explain the result, and why was it ruled out?
7. **Next checks are actionable.** "Re-run in 30 days with fresh cohort data from Q2" not "monitor going forward."

## Output Contract

**Recommendation block**
- Answer-first: one sentence stating the recommended action and expected outcome.
- Ranked options if multiple paths exist, with explicit trade-offs per option.
- Each recommendation tied to a specific validated finding (Gate 2 → Gate 3).
**Evidence summary**
- Key findings table: finding, driver, contribution percentage, confidence, lens applied.
- Narrative paragraph connecting findings back to the decision frame.
**Driver tables**
- Contribution breakdown: driver name, absolute effect, relative effect, confidence interval.
- Segment comparison table when segmentation was applied.
**Charts**
- Trend chart with the decision window highlighted.
- Driver waterfall or decomposition chart.
- At least one segmentation chart.
- `$chart-rules` governs all chart output.
**Caveats and confidence**
- Per-finding confidence rating with brief justification.
- Known data gaps, sample limitations, period edge cases.
- Statement of what would change the conclusion and under what conditions.
**Reproducibility notes**
- Source tables, date ranges, and filters used.
- Query or script references.
- Parameter choices and rationale.

## Skill Dependencies

- `$chart-rules`: Auto-loaded when generating charts
- `$metric-diagnostics`: Load when recommendation depends on validated metric movement
- `$build-report`: Auto-loaded in report mode

## Available Tools

- `preflight.py`：项目预检信封，加载上下文、语义层、source routing
- `validation.py`：验证门——证据覆盖、源安全、图表契约、schema 合规
- `execution.py`：本地 Python 代码执行，生成表格和图表
- `chart_contract.py`：图表类型验证和意图兼容性检查
