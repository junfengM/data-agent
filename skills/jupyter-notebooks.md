Name: Jupyter Notebooks
Use When: The user needs a reproducible analysis notebook, wants to inspect analysis code, or needs an audit trail for analytical work.

# Jupyter Notebooks

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. **Determine notebook purpose.** Classify the request before writing a single cell. Three modes:
   - **Exploratory analysis:** code-first with heavy inline comments. Focus on investigation paths, not polish.
   - **Reproducibility record:** every step documented, fully re-runnable from scratch. The notebook is the audit trail.
   - **Stakeholder deliverable:** narrative flow with findings highlighted, charts embedded, prose connecting evidence to conclusions.
   Purpose determines cell structure, prose depth, and whether intermediate exploration cells are kept or cleaned up.

2. **Plan notebook structure.** Outline the cell sequence before writing any code:
   - Title cell: markdown with notebook title, question under investigation, date generated, and data source inventory
   - Reproducibility note: markdown cell at the top explaining Python version, required packages, and how to re-run
   - Environment setup: imports and path configuration — all paths relative to project root, no hardcoded absolute paths
   - Data loading: load each source, display `df.head()` and `df.info()`, verify shapes match expectations
   - Data quality: run profiling checks inline per `$analyze-data-quality`. Surface nulls, duplicates, grain issues before analysis.
   - Analysis cells: SQL via DuckDB or pandas operations. Each cell starts with a comment explaining what and why.
   - Visualization: charts per `$chart-rules`. Every chart followed by a markdown cell with the one-line takeaway.
   - Findings summary: one markdown cell per key finding, leading with the conclusion and citing supporting chart/table cells.
   - Caveats: specific data gaps, assumption boundaries, methodology limitations, and what the analysis cannot answer.
   - Next steps: follow-up questions this analysis raises, with suggested data or methods to investigate further.

3. **Write environment setup.** Import only what is needed: pandas, DuckDB, plotly. Set pandas display options for readable output. Configure a `PROJECT_ROOT` variable via `pathlib.Path(__file__).resolve().parent` or equivalent so all data paths resolve relative to project root. Never embed `/Users/...` or `C:\...` paths.

4. **Load and document data sources.** For each dataset, write a markdown cell describing:
   - What this source is and where it came from (file path relative to project root)
   - When it was refreshed or extracted (file modification date or ingestion timestamp)
   - Expected row count and column description
   Follow with a code cell that loads the file, displays `df.head()` and `df.info()`, and asserts the shape against expectations. If shapes mismatch, surface the discrepancy in a markdown cell before continuing.

5. **Embed data quality checks inline.** Do not skip quality checks — the notebook is the audit trail. Run per `$analyze-data-quality`:
   - Completeness: null counts and null rates per column, flag columns above 20% null threshold
   - Duplicates: exact duplicate count and rate as percentage
   - Grain verification: state what each row represents, check for mixed grain or subtotal rows
   - Freshness: identify the most recent date column, compare against expected refresh cadence
   Surface all issues in a markdown cell before analysis proceeds. This front-loads data trustworthiness for the reader.

6. **Build analysis cells.** Write SQL via DuckDB or pandas operations. Each code cell must:
   - Start with a comment stating what the cell computes and why (not just what, but the analytical intent)
   - Be self-contained — no hidden state from cells run out of order; re-import or re-derive if needed
   - Include assertions or validation checks on intermediate results (check row counts, value ranges, join match rates)
   - Produce output (printed DataFrame, summary stats) that directly supports a finding in the summary section
   Markdown cells between analysis blocks connect the steps — explain why the next computation follows from the previous result.

7. **Embed charts inline.** Generate charts per `$chart-rules` chart type mapping. Use plotly: `fig.write_html("chart_name.html")` for interactive rendering. Matplotlib is currently disabled — do not use `plt.savefig()` or static PNG charts. Every chart must have:
   - Title describing what the chart shows, not how it was made
   - Axis labels with units ($M, %, K users)
   - Source attribution in the chart footnote or following markdown cell
   - A markdown cell immediately after stating the one-line takeaway (not "Sales by Region" but "East leads with 34% of revenue")

8. **Write findings summary.** One markdown cell per key finding, ordered by importance. Lead with the conclusion, then cite the specific chart, table, or code cell that supports it. Include magnitude, direction, and uncertainty. Example: "Monthly active users declined 12% MoM (from 45K to 39.6K), driven primarily by a 22% drop in organic acquisition channel (see Chart 2, Cell [7]). The decline exceeds the 5% seasonal baseline for this period."

9. **Document caveats and next steps.** Caveats markdown cell must list specific gaps — not generic disclaimers. Include:
   - Data gaps: "Revenue data excludes offline channel X for dates before 2025-03"
   - Assumption boundaries: "Segmentation assumes 7-day attribution window; 30-day window would shift allocation by ~8%"
   - Methodology limits: "Correlation analysis does not establish causation; A/B test required to confirm"
   - Questions the analysis cannot answer: "Cannot determine whether churn increase is from pricing change or competitor launch without additional data"
   Next steps cell: list 2-4 follow-up questions with suggested data or methods.

10. **Save and verify.** Write the `.ipynb` file using `server/app/tools/notebooks.py` to the project artifacts directory under the current run ID. Set metadata fields: `kernelspec` to the project Python environment, `language_info` to Python 3. Open the saved notebook and confirm:
    - All cells execute in order from top to bottom without errors
    - All outputs render correctly (DataFrame displays, chart images, markdown formatting)
    - Cell execution numbers are sequential (no skipped or out-of-order cells)

## Output Contract

- `.ipynb` notebook file saved to project artifacts directory under the current run ID, named `analysis-notebook.ipynb`
- Notebook structure in order: title → reproducibility note → environment setup → data loading per source → quality checks → analysis cells → charts with takeaways → findings summary → caveats → next steps
- All code cells are self-contained and runnable top-to-bottom with no hidden state dependencies between cells
- All data file paths are relative to project root (using `PROJECT_ROOT / "data/file.csv"`), never absolute or machine-specific
- Every data source has a markdown description cell (what it is, origin, refresh date, expected row count)
- Every code cell has a comment explaining what it computes and why — no unexplained code blocks
- Charts are embedded inline with titles, axis labels, units, and source attribution per `$chart-rules`
- A "How to re-run" markdown cell at the top lists: Python version, required packages (pandas, DuckDB, plotly), and data refresh date
- Notebook metadata includes `kernelspec` and `language_info` pointing to the project Python environment
- Reproducibility: notebook can be re-executed from top to bottom and produce identical results

## Skill Dependencies

- `$chart-rules`: For chart type selection, rendering conventions, and annotation rules when embedding charts in notebook cells
- `$analyze-data-quality`: For data profiling checks embedded as notebook quality cells before analysis
- `$visualize-data`: For chart design decisions and visual QA before embedding charts in cells

## Quality Bar

Before signing off, confirm:

1. Notebook executes from top to bottom without errors — every cell in sequence produces expected output. No skipped cells, no runtime exceptions.
2. All data file paths are relative to project root — no `/Users/...` or `C:\...` paths in any cell. Use `PROJECT_ROOT` variable consistently.
3. Every data source has a markdown description cell stating what it is, where it came from, and when it was refreshed.
4. Every code cell has a comment explaining what it computes and why. No unexplained code blocks — the reader should understand the analytical intent without decoding raw code.
5. Charts have titles, axis labels, units, and source attribution inline. No bare chart images without surrounding context. Every chart is followed by a markdown cell stating the takeaway.
6. A "How to re-run" section at the top lists Python version, required packages, and data refresh date. Notebook metadata includes `kernelspec` pointing to the project environment.

## Available Tools

- `execution.py`：本地 Python 代码执行
- `preflight.py`：项目预检信封
