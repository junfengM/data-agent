Name: Chart Rules
Use When: Analysis steps need to generate charts or select visualization types. Always load this before writing chart-generating code in the plan.

# Chart Selection Rules

## Mandatory Pre-Answer Gate

Before generating charts: load `$user-context` and verify source data is profiled and trusted.

## Deterministic Mapping

When writing analysis code that generates charts, follow these rules. Do not invent chart types — pick from this table based on the data characteristics.

| Data Pattern | Chart Type | Library | Example Use |
|---|---|---|---|
| Time series (date/numeric x, numeric y) | `line` | native visual_report chart | Daily revenue, weekly active users |
| Category comparison (≤20 categories) | `bar` (horizontal) | native visual_report chart | Revenue by region, sales by product |
| Category comparison (>20 categories) | `bar` (vertical) or `leaderboard` | native visual_report chart | Top 50 products |
| Part-to-whole (≤6 categories) | `pie` | native visual_report chart | Revenue share by channel |
| Part-to-whole (>6 categories) | `stacked bar` | native visual_report chart | Revenue by 8 product lines |
| Distribution of a single numeric | `histogram` or `box plot` | native visual_report chart | Order value distribution |
| Relationship between two numeric | `scatter` | native visual_report chart | Spend vs. revenue correlation |
| KPI summary (1-8 metrics) | metric card / metric strip | native visual_report card | Dashboard header |
| Ranking (top N) | `leaderboard` (horizontal bar, sorted) | native visual_report chart | Top 10 customers |
| Cumulative over time | `area` | native visual_report chart | Cumulative revenue, running total |
| Funnel stages | `funnel` | native visual_report chart | Conversion funnel |
| Waterfall (additive breakdown) | `waterfall` | native visual_report chart | Revenue bridge, profit decomposition |

## Visual Report Output Contract

The primary report surface is a `visual_report` artifact built from manifest + snapshot data.

For every important chart:

1. Save the reviewed data table as CSV, for example `monthly_revenue_chart_data.csv`.
2. Print the table columns and row count so the runner can expose deterministic previews.
3. Include a `chart_specs` entry in the final JSON response that points to those columns.
4. Reference every primary chart from the narrative report at the point where it supports a claim.
   - For file charts such as Plotly HTML, the final `report_md` MUST include an exact Markdown link using the generated asset filename:
     `[业务可读图表标题](chart_name.html)`.
   - Do not only list chart_specs; chart_specs are not visible in Web Report unless the report body references the chart.
   - Do not append all charts at the end as a generic gallery unless they are explicitly secondary appendix evidence.

Example `chart_specs` entry:

```json
{
  "name": "monthly_revenue_trend",
  "chart_type": "line",
  "intent": "trend",
  "x_field": "month",
  "y_fields": ["revenue"],
  "title": "Monthly Revenue Trend"
}
```

PNG or HTML charts may be generated as secondary attachments when a native chart cannot express the visual, but they should not be the main report surface.

For Web Report / report mode:

- Primary charts MUST be Plotly `.html` assets unless the user explicitly requests static images.
- The final `report_md` MUST include exact Markdown links to generated `.html` chart assets:
  `[业务可读图表标题](chart_name.html)`.
- Do not generate Matplotlib PNG charts for primary report evidence.
- PNG/JPG/SVG image charts are disabled for generated analysis by default and should only appear as legacy or explicitly requested static attachments.

## Chart Annotation Rules

Every chart spec should include enough context for the final report:

```python
print(f"Chart: {chart_name} — {what_it_shows}")
print(f"  Source: {dataset_name}, {row_count} rows")
print(f"  Key finding: {one_line_takeaway}")
```

## Visual Contracts

Every chart should include in the report:

- **Title:** what the chart shows
- **Subtitle/Takeaway:** the one-line insight (not "Sales by Region" but "East leads with 34% of revenue")
- **Source:** dataset filename and row count
- **Units:** axis labels with units ($M, %, K users)
- **Caveats:** data limitations (truncated, estimated, sampled)

## Rules

1. NEVER use a pie chart for >6 categories — use stacked bar instead
2. NEVER use a line chart for unordered categories — use bar
3. Time series charts MUST use date/time on x-axis with proper sorting
4. Chart titles must describe WHAT, not HOW — "Weekly Revenue by Region" not "Line chart of revenue"
5. Prefer native `visual_report` chart specs over standalone PNG/HTML chart files
6. Do not inline base64 images

## Available Tools

- `chart_contract.py`：图表类型验证（18 canonical types）、意图兼容性映射、混合尺度检测、混合指标检测
