Name: Analyze Data Quality
Use When: The user needs to assess source data trustworthiness before analysis, verify a dataset is fit for purpose, or diagnose data problems.

# Analyze Data Quality

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. **Profile source.** Load the dataset and report:
   - Row count and column count
   - File size and format (CSV, Excel, Parquet, etc.)
   - Ingestion timestamp or file modification date
   - Column names, inferred pandas dtypes, and memory usage
   - Presence of index or row-number columns that may indicate prior processing
   Use `df.info()` and `df.describe(include="all")` as the baseline.
   Also check for encoding issues: non-ASCII characters in column names, mixed encodings in text fields, or unparsed date strings.

2. **Check freshness.** Identify the most recent date column or modification timestamp. Compare against the expected refresh cadence (e.g., daily, weekly, monthly). If the dataset has no date column, check file modification time instead. Flag data as stale when the gap exceeds 2× the expected interval. Record both the last observed date and the staleness conclusion.

3. **Verify grain.** State what each row represents (e.g., one order, one user-day, one store-month). Check for mixed grain by:
   - Grouping by candidate primary-key columns and looking for duplicate groups
   - Spot-checking row counts against expected cardinality (e.g., 7 rows for "weekly by weekday" is fine; 3 rows for "daily over a month" is not)
   - Flagging rows that appear to be subtotals, grand totals, or blank separators

4. **Detect completeness.** For each column, compute:
   - Null count and null rate (`null_pct`)
   - Presence of sentinel values (empty strings, "N/A", "-", 0 as missing for certain domains)
   - Overall completeness score: `(1 − total_nulls / (rows × cols)) × 100`
   Sort columns by null rate descending. Flag any column exceeding a 20% null-rate threshold. Report the top 5 offenders.

5. **Find duplicates.** Check for exact duplicate rows with `df.duplicated()`. Report duplicate count and rate as percentage of total rows. For columns likely to be unique identifiers (e.g., order_id, user_id), check for duplicate values within that column. If requested, run fuzzy duplicate detection on text columns using Levenshtein distance — report near-duplicate pairs above the configured threshold.

6. **Check schema.** When a reference schema or prior snapshot is available:
   - Compare column names: report columns present in one but not the other
   - Compare column types: flag any type change (e.g., float → object, date → string)
   - Flag unexpected columns that may indicate a pipeline change
   - Report this as schema drift with a before/after summary
   When no reference schema exists, document the observed schema as the new baseline.

7. **Validate joins.** If the analysis spans multiple datasets:
   - List the join keys declared or implied by the user
   - For each join key pair, compute unmatched rates on both sides
   - Report: left-only rows, right-only rows, matched rows, and match rate
   - Flag asymmetric joins where one side has significant unmatched data

8. **Detect outliers.** For numeric columns:
   - Compute IQR (Q1, Q3) and flag values beyond `Q1 − 1.5×IQR` and `Q3 + 1.5×IQR`
   - Check for impossible values: negative quantities, future dates, ages > 120, negative revenue
   - Report outlier count, percentage, and value range per column
   For categorical columns: list unique values and flag unexpected or malformed entries.

9. **Compare sources.** When the same logical data appears in multiple sources:
   - Compare row counts and summary statistics (mean, median, min, max)
   - Compute row-level agreement on shared key columns
   - Flag discrepancies > 5% between sources

10. **Assign trust rating.** Synthesize findings into a trust rating:
    - **Trusted** — all checks pass. Null rates < 5%, no duplicates, schema matches expectations, freshness within window, no outlier concerns.
    - **Use with caution** — moderate issues exist. Null rates 5–30%, duplicates < 5%, minor schema drift, or some stale segments. List each caveat explicitly.
    - **Do not use** — critical failures. Null rates > 30%, duplicates > 10%, join keys broken, schema unrecognizable, or freshness gap > 4× expected cadence.

## Output Contract

- **Trust rating** — one of Trusted / Use with caution / Do not use, with evidence summary citing specific findings
- **Source profile** — rows, columns, file size, format, ingestion date, memory footprint
- **Freshness assessment** — last observed date, expected cadence, staleness flag with gap details
- **Completeness report** — overall score plus a table of per-column null rates (top columns by null rate, descending)
- **Duplicate detection** — exact duplicate count and rate as percentage; fuzzy duplicate summary if applicable
- **Schema validation** — expected vs. actual column names and types with drift notes; or "no reference schema — observed schema documented as baseline for future drift checks"
- **Outlier summary** — list of affected columns with outlier counts, percentage of total, and value range (min–max for each outlier cluster)
- **Join compatibility** — per-join-key match rates, left-only counts, right-only counts, match percentage
- **Source comparison** — row count differences and summary stat deviations when multiple sources cover the same data
- **Recommendations** — ranked cleaning actions with estimated impact (e.g., "drop 450 exact duplicates → removes 0.02% of rows", "impute 32% nulls in revenue column with median")

## Skill Dependencies

- `$chart-rules`: Auto-loaded — for visualizing null distributions (bar charts by column), outlier box plots, and duplicate rate summaries

## Quality Bar

Before signing off, confirm:

1. Every column in the source has been profiled: name, dtype, null count, and null rate.
2. Freshness has been compared against a known cadence, or explicitly marked "unknown — no date column found in source."
3. Row grain has been stated in one sentence and verified against the data (no mixed aggregation levels).
4. Duplicate rate is reported as a percentage of total rows, not just an absolute count.
5. Any schema drift is documented with concrete before/after differences (column names added, removed, or type-changed).
6. The trust rating names at least one specific finding per dimension that failed (e.g., "Use with caution — 28% nulls in discount_amount + 3% exact duplicates + schema drift: discount_amount changed float→object").
7. Every column with null rate above 20% appears in the completeness table, not just the top 5.
8. Outlier detection has been run on all numeric columns, not just the first few — and none are skipped without a stated reason.

## Available Tools

- `preflight.py`：项目预检信封
- `execution.py`：本地数据分析和质量检查代码执行
