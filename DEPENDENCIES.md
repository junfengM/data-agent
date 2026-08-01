# Lane Placeholders

Placeholders are abstract source references that skills use to declare what kind of data they need, without hardcoding file paths or tool names. The router resolves a placeholder to the best available source at runtime through source discovery and the semantic layer.

Skills reference placeholders by their `~~name`. Each placeholder describes the category of data, the file formats it expects, and which helper skills validate or enrich that data.

# Placeholders

## ~~structured_data
### Structured Data
- **description**: Tabular datasets — transactions, orders, master data, log extracts
- **sources**: CSV, Excel (.xlsx), DuckDB tables, SQLite databases
- **helper skills**: `$analyze-data-quality`, `$validate-data`

## ~~product_analytics
### Product Analytics
- **description**: Event tracking exports, feature usage logs, funnel step counts, retention cohorts
- **sources**: CSV event logs, Excel usage summaries, DuckDB event tables
- **helper skills**: `$product-analysis`, `$metric-diagnostics`

## ~~business_metrics
### Business Metrics
- **description**: Revenue reports, cost data, P&L extracts, budget files, financial summaries
- **sources**: CSV, Excel, SQLite financial tables
- **helper skills**: `$kpi-reporting`, `$metric-diagnostics`, `$design-kpis`

## ~~user_research
### User Research
- **description**: Survey results, interview notes, NPS scores, user feedback transcripts
- **sources**: CSV survey exports, Excel NPS tables, Markdown interview notes
- **helper skills**: `$gather-business-context`, `$product-analysis`

## ~~market_data
### Market Data
- **description**: Industry reports, competitor data, benchmark tables, market share estimates
- **sources**: CSV benchmark files, Excel competitor matrices, DuckDB reference tables
- **helper skills**: `$market-sizing`, `$gather-business-context`

## ~~analysis_artifacts
### Analysis Artifacts
- **description**: Prior reports, dashboards, notebooks, chart exports from earlier runs
- **sources**: Markdown reports, Jupyter notebooks (.ipynb), chart images, workspace artifacts
- **helper skills**: `$build-report`, `$jupyter-notebooks`, `$visualize-data`

## ~~project_context
### Project Context
- **description**: Semantic layer definitions, project config, metric formulas, dimension catalogs
- **sources**: `config/semantic-layer.yaml`, `config/agent-manifest.yaml`, project context files
- **helper skills**: `$user-context`, `$gather-business-context`
