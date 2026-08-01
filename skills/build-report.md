Name: Build Report
Use When: The user needs a polished analytical report with findings, evidence, charts, caveats, and source metadata.

# Build Report

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. Define audience, decision, and scope.
2. Inspect data sources and constraints.
3. Run analysis with reproducible code or SQL.
4. Build charts and tables that support the narrative.
5. Write an answer-first report.
6. Include caveats, source metadata, and next steps.

## Audience Specification

Every report addresses a primary audience. Audience choice determines depth, evidence burden, and format. If the user does not specify, ask before building.

Executive: KPI narrative with risk flags and decisions needed. 1-page summary layout with metric cards and red/amber/green status indicators. Omit methodology unless requested. Lead with the number, not the story.

Technical: Full methodology, data quality notes, and reproducibility path. Include query details, sample sizes, validation steps, and failure modes. Assume the reader will verify or extend the analysis.

Stakeholder: Decision framing with clear options and a recommendation. Evidence tied to each option in a comparison table. Callouts for trade-offs, unknowns, and assumptions that could flip the recommendation.

Mixed audience: default to stakeholder format with a technical methodology appendix. When audience is ambiguous, confirm before building.

## Report Spine

Answer-first structure. Lead with the conclusion, then build the evidence.

1. Answer-first: State the main finding in the first paragraph. No buildup, no background first.
2. Evidence cascade: Data tables and charts that directly support each claim. Every claim without evidence gets flagged or removed.
3. Interpretation: What the evidence means for the decision. Do not just describe what the chart shows — explain the implication.
4. Caveats: Data quality gaps, assumption boundaries, methodology limits. Be specific ("sales data excludes channel X for dates before Y"), not generic ("data may be incomplete").
5. Next checks: Questions the current data cannot answer. Follow-up analysis paths if the reader needs to go deeper.

Spine-to-block mapping: answer-first = opening prose block, evidence cascade = tables + charts, interpretation = follow-up prose, caveats = callout block, next checks = closing section.

## Delivery Mode Selection

Choose mode based on audience and consumption context. Default is structured_report.

structured_report: Block-based layout with prose, tables, charts, and metric cards assembled in narrative order. Rich formatting with section headers and callout blocks. Default for multi-section analytical reports.

visual_report: Management-ready visual page layout with KPI cards, charts, rankings, contribution decomposition, insight callouts, risk panels, and next-action panels. Use this whenever the user asks for a business recap, operating review, monthly report, executive summary, management report, performance overview, or shareable report. This mode is optimized for screenshot / image export.

markdown: Flat single-file Markdown. Good for version control, git diffs, pasting into chat tools. Tables and charts rendered inline. No rich layout blocks. Use for quick summaries or chat delivery.

html: Portable single-file with embedded styles, tables, and chart images. Good for sharing as email attachment or viewing in browser without tooling dependencies. Use for external stakeholder distribution.

Mode selection: visual_report for management-facing business reports, structured_report for deep analysis, markdown for review/diff workflows, html for portable sharing.

## Visual Report Layout Contract

For `visual_report`, do not produce a table-heavy Markdown report. The final report must be a visual reading surface assembled from reusable blocks. Tables are supporting evidence only.

Required block mix for management-style visual reports:

1. KPI grid / metric strip: 4-12 headline metrics with current value, comparison value, delta, and direction.
2. Driver bridge / change decomposition: explain the main metric movement with positive and negative contributors.
3. Trend panel: show the time path when a date grain is available.
4. Leaderboard pair: show Top growth and Top drag contributors side by side for category, brand, SKU, channel, or segment.
5. Composition panel: show mix / structure such as channel split, new vs existing customers, category mix, or product age.
6. Insight banner: one sentence of business interpretation after each major evidence group.
7. Risk panel: show risks, caveats, or data gaps with amber/red treatment.
8. Next-action list: 3-5 concrete follow-up actions.
9. Page summary: close each page or section with 3-4 short management conclusions.

Visual block type names the reporter may emit in the manifest block stream:

- `kpi_grid`
- `delta_bridge`
- `leaderboard_pair`
- `trend_panel`
- `composition_panel`
- `insight_banner`
- `risk_panel`
- `next_action_list`
- `page_summary`

Each visual block must keep evidence ids, source metadata, units, date windows, and metric definitions when available. If the current renderer does not yet support a proposed block type, fall back to the closest supported combination of `metric-strip`, `chart`, `table`, `markdown`, and `callout`, but keep the visual intent in the block title and narrative.

## Claim-to-Visual Evidence Contract

In `visual_report` mode, the goal is not "text plus some decorations"; the report must make conclusions readable through visual evidence.

- Every core conclusion must be backed by at least one chart, metric card, or evidence-backed visual block.
- At least one headline conclusion should directly cite chart evidence when the data supports a chartable pattern such as trend, ranking, composition, decomposition, distribution, relationship, or funnel.
- Do not let the executive summary rely only on a dense table. If the only available evidence is tabular, extract the conclusion into a KPI card, compact ranking, composition block, or chartable dataset before delivery.
- Surround each major chart or visual block with a one-sentence takeaway that explains the business implication.
- If a conclusion cannot be supported by a chart or visual block, mark it as caveated, move it to an appendix, or remove it from the core narrative.

## Anti-Table Guardrail

In `visual_report` mode:

- Do not place two dense tables consecutively.
- Do not use a table as the first evidence block unless the user explicitly asks for a table.
- Do not represent KPI overview as a table; use metric cards.
- Do not represent Top/Bottom lists as full-width dense tables when a compact ranking block can show the same information.
- Do not let tables occupy more than one third of the main report body.
- Every table must answer a specific audit/evidence question and should be visually secondary to conclusions and charts.
- If tables occupy more than half of the main flow, visual_report validation should fail rather than silently delivering a table-first artifact.

## Report Depth Gate

Before building the report, apply these stop conditions. A report is too thin and must be expanded if:

- The spine has only a title, an executive summary, and one chart or table — stop and expand the evidence path before rendering unless the user explicitly asked for a brief.
- Quantitative findings lack visible metric/cohort definitions before those definitions are needed to interpret the evidence.
- A comparative report lacks segment-level interpretation — do not present only aggregate values when segments are available.
- A causal-adjacent or behavior-difference report lacks at least one validation, sensitivity, or limitation note near the finding it qualifies.
- A report with only one narrative block plus chart/table evidence is too thin, unless the user explicitly requested a brief or a single-chart readout.
- A management-facing report has mostly tables and no KPI grid, driver bridge, leaderboard, trend, or action panel.
- A visual report has core conclusions but none of them are supported by chart, metric, or visual-block evidence.

The executive summary does not count as the evidence section.

## Block Assembly Rules

Reports are assembled from composable blocks. Order blocks in narrative sequence following the report spine.

Prose blocks: Narrative text sections. Keep paragraphs to 3-5 sentences. One idea per paragraph. Use plain language unless audience is technical. Prefer active voice.

Table widgets: Sortable data tables with column-aligned numbers. Caption includes source dataset name and date range. Right-align numeric columns, left-align text columns. In visual reports, tables must be compact evidence blocks, not the main presentation surface.

Chart widgets: Visualizations with title, axis labels, legend, and source note. Follow `$chart-rules` design conventions. Every chart answers a specific question stated in the surrounding prose. Load `$visualize-data` for chart QA.

Metric cards: Single-KPI display showing current value, comparison period value, variance, and trend arrow. Red, amber, or green status based on target threshold. Group related cards in a row.

Visual ranking blocks: Use for Top/Bottom contributor lists. Keep labels concise, show delta and contribution, and use green/red direction treatment.

Driver bridge blocks: Use for explaining metric movement. Separate positive and negative contributors, include total change, and state the business interpretation in a subtitle or callout.

Callouts: Blockquoted highlights that flag risks, surface context, or emphasize a key takeaway. Use sparingly — 2-3 per report maximum unless using dedicated risk/action panels.

Source notes: Every evidence block must carry source metadata: dataset name, date range, query or notebook path, refresh frequency. No anonymous data in reports. If source cannot be cited, flag the block as unverified.

## Report Evidence Integration Contract

For every table/chart generated by execution and used as evidence:

1. The final `report_md` must integrate the evidence into the relevant narrative section.
2. A claim should be followed by the table/chart that supports it, plus a short takeaway.
3. File charts must appear as exact Markdown links:
   `[业务可读图表标题](asset_name.html)`.
4. Tables must either be rendered as compact Markdown tables or explicitly cited by table name/title with key values.
5. Do not fix missing evidence by appending a generic chart/table list at the end. If evidence is missing from the narrative, rewrite the section.

## Quality Bar

Seven checks before delivery. All must pass. Do not skip any.

1. Claim-to-evidence mapping: Every claim in prose links to a data artifact (table, chart, or metric card) that supports it. Unsupported claims get removed or marked as opinion.
2. Source metadata: Every evidence block includes source dataset, date range, and query path. Full traceability back to raw data.
3. Chart contracts: Charts follow `$chart-rules`. Titles, axis labels, source notes present. Scale and aggregation method documented.
4. Context caveats surfaced: Data gaps, assumption boundaries, and methodology limits appear in the caveat block. Generic disclaimers are not acceptable.
5. Render check: Output renders correctly in the selected delivery mode. Tables align, charts display, links resolve.
6. Reproducibility appendix: All analysis code or SQL paths included. Runnable from project root with documented dependencies.
7. Delivery mode confirmed: Output file matches requested format. No stray artifacts, no debug output, no intermediate files included in delivery.

Additional visual report checks:

8. Visual density: The report contains at least three non-table visual components when enough data is available.
9. Table discipline: The visual report is not dominated by dense tables.
10. Download readiness: The report surface is coherent as a screenshot / exported image without relying on hidden details panels.
11. Core conclusion support: primary conclusions are backed by chart, metric, or evidence-backed visual blocks; table-only support is not enough for the main narrative.

## Completion Checklist

Confirm before delivering the report artifact:

- [ ] Audience identified and format matches audience type
- [ ] Spine intact: answer-first flow, no buildup before conclusion
- [ ] Delivery mode selected and render check passed
- [ ] All required blocks present: prose, evidence (tables or charts), caveats, source notes
- [ ] Visual reports include KPI grid, driver/ranking/trend/composition components where supported by data
- [ ] Visual report core conclusions cite chart, metric, or visual-block evidence
- [ ] Quality bar passed: all checks confirmed
- [ ] `$chart-rules` loaded if report contains charts
- [ ] `$visualize-data` loaded for chart QA if charts present

## Output Contract

- Answer-first summary: 3-5 sentence conclusion. No jargon unless audience is technical.
- Evidence tables with source metadata: dataset name, date range, and query path on every table caption.
- Charts with titles, axis labels, legend, and source notes. Per `$chart-rules` design conventions.
- Metric cards: target vs actual, variance percentage, trend direction, and RAG status.
- Visual-report blocks: KPI grid, driver bridge, ranking pair, trend/composition panel, insight/risk/action blocks when user asks for a management-facing or shareable report.
- Caveat block: specific data gaps, assumption boundaries, and methodology limits.
- Reproducibility appendix: all analysis code or SQL paths, runnable from project root. Specify Python version and package dependencies.
- Source inventory: list every dataset used, with refresh date and row count.
- Report metadata: audience type, decision question, date generated, data freshness window.

## Skill Dependencies

- `$chart-rules`: Auto-loaded when report includes charts
- `$visualize-data`: Load for chart design and QA before embedding

## Available Tools

- `preflight.py`：项目预检信封
- `validation.py`：验证门——产物可渲染性、源安全、schema 合规
- `chart_contract.py`：图表类型验证和意图兼容性检查
- `execution.py`：本地 Python 代码执行
