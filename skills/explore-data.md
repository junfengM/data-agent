Name: Free Insight Discovery
Use When: The user provides detailed row-level data and asks for open-ended findings rather than a named metric, KPI, or pre-framed business question. Trigger phrases: "有什么发现", "自由洞察", "分析一下这个数据", "看看有什么规律", "find insights", "what stands out", "analyze this spreadsheet".

# Free Insight Discovery

Use this skill when the user provides detailed data or a broad data source and asks for open-ended findings rather than a named metric diagnostic, KPI design, dashboard, or pre-framed business decision.

This skill is an exploratory workflow, but it is not permission to speculate. It turns row-level data into a small set of ranked, source-backed insights with evidence, caveats, and next actions.

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Supporting Skills

- Use `$analyze-data-quality` before ranking insights when data quality could change conclusions.
- Use `$visualize-data` for the final top insights when visuals improve readability.
- Use `$build-report` when the user requests a durable artifact or when the findings need stakeholder-ready narrative.
- Use `$validate-data` before finalizing surprising, high-impact, or decision-relevant claims.
- Use `$product-analysis` when the exploratory findings need to become a recommendation for a specific decision.
- Use `$metric-diagnostics` when exploration reveals a specific metric movement that needs root-cause diagnosis.

## Workflow

### 1. Establish Dataset Meaning

Before calculating insights, identify what the dataset appears to represent.

Determine:
- unit of analysis / grain: one row per order, user, event, session, ticket, transaction, product, account, etc.
- time range and primary time field
- likely identifier fields
- numeric measure fields
- categorical dimension fields
- boolean / status / label fields
- sensitive fields that should not be exposed
- whether the dataset is complete enough for open-ended exploration

If the grain is ambiguous, infer the most likely grain, state the assumption, and avoid conclusions that depend on uncertain grain.

### 2. Build A Compact Data Profile

Create a compact profile before mining insights:
- row and column counts
- column types and likely semantic roles
- date coverage and recent-period completeness
- missingness by important field
- duplicate rate by likely key or composite key
- cardinality for categorical fields
- distribution summaries for numeric fields
- obvious impossible values, sentinel values, or outliers

Do not dump the profile as raw output. Use it to decide which findings are trustworthy.

### 3. Construct Candidate Business Metrics

From the grain and fields, create candidate metrics that fit the dataset.

Examples:
- order data: revenue, orders, buyers, AOV, refund rate, discount rate, repeat purchase rate
- event data: active users, event count, conversion rate, funnel step conversion, sessions per user
- user data: new users, activation rate, retention proxy, paid conversion, segment mix
- support data: ticket volume, resolution time, reopen rate, SLA breach rate, CSAT
- product catalog data: sales, stockout risk, price bands, concentration, category mix

Prefer metrics with clear denominators. Label derived metrics and assumptions.

### 4. Mine Candidate Insights Systematically

Search for findings across these insight types. Use only the types supported by the data shape.

**Insight Taxonomy:**

| Type | Question | Common methods | Good chart |
|---|---|---|---|
| Trend | What changed over time? | time aggregation, rolling average, period-over-period | line |
| Segment difference | Which groups differ most? | groupby, normalized rates, top/bottom N | bar |
| Anomaly | What is unusually high/low? | robust z-score, IQR, baseline comparison | line with markers, boxplot |
| Contribution | What explains most of total/change? | contribution share, delta decomposition, Pareto | waterfall, Pareto |
| Mix shift | Did composition change? | share-of-total by time, before/after mix | stacked bar |
| Funnel | Where do users drop? | ordered event conversion, step drop rate | funnel |
| Concentration | Is value concentrated? | top-N share, Gini proxy, cumulative share | Pareto, cumulative curve |
| Relationship | Which fields move together? | correlation, binned averages, scatter | scatter, heatmap |
| Data quality | Could the data mislead us? | nulls, duplicates, freshness, invalid values | table |

Rules:
- Prefer absolute impact plus rate, not just percent change.
- Never promote a finding from a tiny denominator without caveat.
- Treat correlations as hypotheses, not causes.
- Compare against a meaningful baseline.

For each candidate insight, store:
- metric and dimension used
- comparison baseline
- effect size
- sample size / coverage
- supporting rows or aggregate table
- caveat
- potential business implication

### 5. Rank Insights

Rank candidates before presenting them. Score each candidate 1-5 on each axis:

**Impact:**
- 5 = material revenue/user/conversion/risk impact.
- 3 = noticeable but bounded impact.
- 1 = descriptive or tiny impact.

**Surprise:**
- 5 = far from baseline, recent regime shift, or outlier among peers.
- 3 = moderately different.
- 1 = expected or obvious.

**Confidence:**
- 5 = large sample, clean fields, stable denominator, verified calculation.
- 3 = adequate sample with caveats.
- 1 = small sample, missing fields, ambiguous grain, or incomplete recent data.

**Actionability:**
- 5 = clear owner and lever.
- 3 = plausible follow-up but not an immediate action.
- 1 = interesting but no clear action.

**Freshness:**
- 5 = current or emerging.
- 3 = relevant but not recent.
- 1 = old or static.

**Priority Score:**
```
priority_score = impact * 0.35 + surprise * 0.20 + confidence * 0.25 + actionability * 0.15 + freshness * 0.05
```

Do not rank low-confidence findings above high-confidence findings unless the caveat is explicit and the impact is very high.

### 6. Filter Weak Or Misleading Findings

Do not promote findings that are likely noise.

Filter or downgrade findings when:
- sample size is too small
- the effect is only percentage growth from a tiny base
- the recent period may be incomplete
- missing or unknown categories could change the conclusion
- the insight depends on an ambiguous grain or denominator
- multiple-comparison mining makes the pattern likely to be accidental
- a correlation is being interpreted as causation
- the issue is purely descriptive and not business-relevant

When a weak finding is still useful, label it as follow-up rather than a key finding.

### 7. Validate Final Findings

Before final answer or report, run a validation pass:
- every key finding has a metric, denominator, comparison, and source
- every major claim can be traced to a calculation or aggregate table
- caveats are visible, especially quality gaps and incomplete recent data
- no sensitive row-level data is exposed unnecessarily
- visuals match the stated takeaway
- recommendations do not overreach the evidence

### 8. Produce The Handoff

Default output structure:

```md
## Dataset readout

- Grain assumption: {one row per ...}
- Rows/columns: {n} rows, {m} columns
- Time range: {start} to {end}
- Important fields: {fields}

## Quality notes affecting interpretation

- {quality issue or 'No major quality blocker found in quick checks'}

## Top insights

### 1. {finding}

- Evidence: {metric, comparison, segment, time range}
- Why it matters: {business implication}
- Confidence: High/Medium/Low — {reason}
- Caveat: {limitation}
- Next action: {action}

## Suggested visuals

- {chart type}: {what it should show}

## Open questions

- {missing field/context that would improve confidence}
```

For stakeholder-ready work, route through `$build-report`. For chat-only work, keep the answer compact and clearly label assumptions.

## Output Standards

Each top insight should use this structure:

```md
### Insight {rank}: {short finding}

- Evidence: {numbers, comparison, segment, time range}
- Why it matters: {business implication}
- Confidence: High/Medium/Low — {reason}
- Caveat: {data or interpretation limitation}
- Next action: {specific follow-up or decision}
```

## Routing Rules

Route to this skill when:
- "这份订单明细有什么关键发现？"
- "帮我自由探索这个 CSV。"
- "What stands out in this transaction-level data?"
- "Find the top insights from this user events table."
- "Analyze this spreadsheet and tell me what the business should notice."
- User uploads a dataset with no specific question.

Do NOT route here when:
- the user already names a metric movement to diagnose: use `$metric-diagnostics`
- the user asks to define KPIs: use `$design-kpis`
- the user asks for a dashboard surface first: use `$build-dashboard`
- the user asks only for quality checks: use `$analyze-data-quality`
