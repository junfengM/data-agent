Name: Validate Data
Use When: Analysis is complete and ready for stakeholder delivery — validates methodology, calculations, conclusions, and evidence quality before handoff.

# Validate Data

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. Review the analysis scope and audience.
   - What question was asked and what decision does it support?
   - Who is the audience and what level of rigor do they expect?
   - Confirm the analysis plan matches the request — no scope creep, no unasked tangents.

2. Verify metric definitions against the semantic layer.
   - For each metric in the analysis, confirm its definition, formula, grain, and filters.
   - Flag any metric not found in the semantic layer as "derived — unvalidated".
   - Confirm all metric calculations are reproducible from source data.

3. Check source selection and data provenance.
   - Is the right dataset used for each claim? Check freshness: is the data current enough for the decision?
   - Flag stale data (last refresh older than the reporting period), truncated data, or sampled subsets treated as full populations.
   - Verify row counts, date ranges, and schema match documented expectations.

4. Validate query and transformation logic.
   - Review SQL or Python pipelines: joins, filters, aggregations, date ranges, window functions.
   - Check for common errors: unfiltered cross joins, off-by-one date boundaries, missing NULL handling, dedup logic gaps.
   - Run the pipeline against a small known subset and compare to expected output.

5. Verify calculation accuracy with spot checks.
   - Pick 2-3 key reported values. Trace each from raw source through every transformation step to final output.
   - Recompute independently and confirm results match within expected tolerance.
   - If any spot check fails, halt and flag — do not pass validation until root cause is found.

6. Check chart and visualization integrity.
   - Confirm every chart type matches the data pattern per `$chart-rules`.
   - Verify axes are labeled with units, scales start at appropriate baselines, sorting is correct.
   - Check that chart annotations include source dataset, row count, and a takeaway.
   - Flag truncated axes, mismatched chart types, or missing caveats.

7. Map every conclusion back to supporting evidence.
   - For each claim in the analysis: what specific data, table, or chart supports it?
   - Flag conclusions that overreach the data (e.g., correlation stated as causation, sample extrapolated to population).
   - Flag unsupported claims, inference gaps, and opinion presented as evidence.

8. Surface methodology gaps and data quality issues.
   - Note any assumptions made but not verified.
   - Identify data gaps: missing dimensions, incomplete time periods, unjoined tables.
   - Run `$analyze-data-quality` checks: completeness, duplicates, outliers, schema drift.

9. Assign a confidence rating and deliver the validation report.
   - Ready: all checks pass, methodology is sound, evidence supports every conclusion.
   - Share with caveats: minor issues found but do not invalidate the core findings.
   - Needs revision: material errors, unsupported claims, or data quality problems that must be fixed before delivery.

## Output Contract

- Validation report with confidence rating and summary judgment
- Methodology review: audit trail from question to conclusion
- Source verification results: freshness, completeness, provenance for each dataset
- Calculation accuracy checks: which values were spot-checked and results
- Chart and visualization integrity assessment against `$chart-rules`
- Evidence-to-conclusion traceability: each claim mapped to its supporting evidence
- Data quality findings from `$analyze-data-quality`
- Caveats, unresolved gaps, and risks carried forward to the stakeholder deliverable

## Confidence Rating Rules

Assign exactly one rating based on the most severe finding:

| Rating | Criteria |
|--------|----------|
| **Ready** | All checks pass. Metrics are defined and reproducible. Data is fresh and complete. Calculations verified. Charts correct. Every conclusion has direct evidence. |
| **Share with caveats** | Minor issues exist but core findings are intact. Examples: one source is slightly stale but directionally correct; a derived metric lacks semantic-layer registration but logic is sound; one chart has a labeling nit. |
| **Needs revision** | Material problems found. Examples: a key calculation is wrong; a conclusion overreaches the data; a chart misrepresents the data; essential source data is missing or corrupted. |

When assigning Share with caveats, list every caveat explicitly. When assigning Needs revision, specify exactly what must be fixed and why. Never round up — if in doubt between two ratings, choose the lower one.

## Quality Bar

- Every metric used is defined and reproducible from source data, with formula, grain, and filters documented
- Source data profiling confirms completeness and freshness for the reporting period; no stale or truncated data used without flagging
- Spot-checked calculations match reported values; any discrepancy is explained or resolved
- Charts follow `$chart-rules` contracts: correct chart type, annotated, axes labeled with units, source cited, takeaway stated
- Every conclusion has a direct evidence chain with no inference gaps; claims do not overreach what the data can support
- Methodology notes are complete enough for another analyst to reproduce the full analysis independently

## Skill Dependencies

- `$chart-rules`: For chart contract validation — type selection, annotation completeness, rendering checks
- `$analyze-data-quality`: For source data quality checks — completeness, freshness, duplicates, schema validation, outlier detection

## Available Tools

- `validation.py`：确定性验证门——evidence_coverage、source_metadata、schema_compliance、chart_contracts、source_safety、sensitive_payload、completion_mode
- `chart_contract.py`：图表类型验证、意图兼容性、混合尺度检测、混合指标检测
