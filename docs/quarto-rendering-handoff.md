# Quarto Rendering Handoff

Last updated: 2026-06-13

## Purpose

This document records the current Quarto-based Web Report / 网页版报告 delivery path. The project moved away from the custom `delivery_renderer_v2` because the custom renderer produced table-heavy styled Markdown pages and is no longer the preferred or fallback path.

Quarto is now the **only active Web Report renderer**. The previous experimental `delivery_renderer.py` line has been retired and removed from the automatic artifact path.

## Current Status

Accepted direction: **Quarto-only Web Report with deterministic preprocessing and postprocessing.**

Recent implementation sequence:

- `a0001728` — Added initial Quarto renderer as preferred delivery path.
- `307e907` — Added first-H1 title extraction, safe YAML generation, local/system fonts only.
- `56307a9` — Added `from: markdown-raw_html` so raw HTML in generated Markdown is not passed through as executable HTML.
- `0c4e6b1` — Added Quarto preprocessor: duplicate-H1 stripping, callout sections, KPI card grids, and chart iframe postprocessing.
- `12d1507` — Hardened chart href normalization and URL encoding.
- `0980551` — Replaced direct chart-link regex extraction with `html.parser.HTMLParser` for href/text extraction and nested link text handling.
- `f213c32` / `0d3fa10` / `93a75a7` / `b840c89` — Closed the old delivery renderer path: `write_web_report_artifact()` is Quarto-only, Quarto tests updated, `delivery_renderer.py` and its tests removed.

Latest user acceptance: the current Quarto-generated report effect is good enough to continue optimizing on the Quarto line. The previous test Web Renderer line should remain closed.

GitHub workflow runs/status checks were not visible through the connector at review time, so CI must still be verified in GitHub Actions when available.

## Architecture

```text
report_md (complete source Markdown)
  -> quarto_renderer.render_quarto_report()
    -> extract first H1 as YAML title; project_name becomes subtitle when different
    -> preprocess Markdown body
       -> strip duplicate first H1 from body
       -> escape bare --- horizontal rules for YAML/Quarto safety
       -> convert diagnostic/executive/action/risk sections to Quarto callouts
       -> convert small KPI-style tables to fenced-div KPI card grids
       -> preserve wide/detail tables as tables
    -> write web_report.qmd with YAML front matter
       -> from: markdown-raw_html
       -> execute: eval=false, echo=false, warning=false
       -> format.html.toc=true, toc-location=left, embed-resources=true
    -> write quarto_style.css (Chinese business-report stylesheet)
    -> subprocess: quarto render web_report.qmd --to html --output web_report.html
    -> postprocess rendered HTML
       -> replace allowlisted local chart .html links with sandboxed iframes
       -> normalize ./chart.html, assets/chart.html, chart.html to basename
       -> URL-encode asset filenames
    -> return (html, metadata)
  -> run_artifacts.write_web_report_artifact()
    -> write web_report.html only when Quarto succeeds
    -> return None when Quarto is unavailable/fails
```

## Key Files

- `server/app/agent/quarto_renderer.py` — active Web Report renderer, preprocessor, CSS, chart-link postprocessor.
- `server/app/agent/run_artifacts.py` — `write_web_report_artifact()`; now Quarto-only.
- `server/tests/test_quarto_renderer.py` — tests for title extraction, YAML safety, preprocessing, KPI conversion, callout conversion, chart iframe postprocessing, and Quarto-only artifact behavior.
- `apps/web/src/components/ArtifactModule.tsx` — detects `renderer="quarto_html"` as a Web Report artifact.

Retired files:

- `server/app/agent/delivery_renderer.py` — removed.
- `server/tests/test_delivery_renderer.py` — removed.

## Boundaries (Non-Negotiable)

1. **Quarto remains downstream of `report_md`.** It does not change the analysis pipeline, semantic layer, deterministic execution, evidence generation, validation, `markdown_report`, or `visual_report`.
2. **Quarto is an external CLI dependency**, not a Python package. Environments without `quarto` on PATH simply do not emit a Web Report artifact.
3. **Web Report generation is optional and nonfatal.** If Quarto fails, `write_web_report_artifact()` returns `None` and the run can still succeed.
4. **No code execution during render.** The qmd YAML front matter sets `execute.eval=false`, `execute.echo=false`, and `execute.warning=false`.
5. **Raw HTML from generated Markdown is disabled** via `from: markdown-raw_html`. Any iframe insertion must come from deterministic postprocessing of allowlisted local chart assets, not from LLM-authored raw HTML.
6. **Source facts and prose must not be rewritten.** Presentation preprocessing may remove a duplicate first H1, wrap sections in Quarto callouts, and transform small metric tables into visual cards; it must not alter claims, values, evidence, or conclusions.
7. **The original Markdown artifact remains authoritative.** The delivery HTML is a polished reading surface, not a replacement for `markdown_report` or in-app `visual_report`.

## Preprocessor Behavior

### Title handling

- First Markdown H1 becomes YAML `title`.
- `project_name` becomes YAML `subtitle` only when present and different from the title.
- The first matching H1 is stripped from the rendered body to avoid duplicated title blocks.

### Callout conversion

Headings matching these intent patterns are wrapped as Quarto callouts:

- `.callout-important`: 执行摘要, 诊断结论, 诊断报告, 综合判断, 总体评估
- `.callout-tip`: 已验证的驱动因素, 已验证, 后续行动, 建议的后续, 行动建议, 优化建议, 改进措施
- `.callout-warning`: 待关注假设, 待关注, 风险因素, 潜在风险, 需要注意, 待验证

### KPI conversion

Small KPI-style Markdown tables are converted to Quarto fenced-div card grids:

```markdown
:::{.kpi-grid}
:::{.kpi-card}
**Q1总收入**
$883,000
:::
:::
```

Rules:

- Convert only small tables with 2–3 columns and up to 8 body rows.
- Require at least one numeric-looking value.
- Preserve wide/detail tables as normal tables.

### Chart iframe postprocessing

After Quarto renders the HTML, chart links are postprocessed only when all conditions hold:

- href points to a `.html` file;
- the normalized basename exists under `artifacts_dir`;
- `run_id` is present;
- the link is local / artifact-backed.

The replacement iframe uses:

```html
<iframe
  src="/api/runs/<run_id>/assets/<url-encoded-chart-file>"
  loading="lazy"
  sandbox="allow-scripts allow-same-origin">
</iframe>
```

Current implementation uses `html.parser.HTMLParser` for href/text extraction after locating candidate `<a>` chunks. It supports nested text such as `<a><strong>月度</strong>收入趋势</a>`, `./chart.html`, `assets/chart.html`, missing chart preservation, and URL-encoded filenames.

## Metadata

Artifacts generated by Quarto carry:

```json
{
  "renderer": "quarto_html",
  "quarto_available": true,
  "fallback_used": false,
  "fallback_renderer": null,
  "title": "Q1 2024 销售额诊断分析报告",
  "subtitle": "可视化报告 QA"
}
```

Frontend detection: `artifact.data?.renderer === "quarto_html"` triggers Web Report display.
The `ArtifactModule` previews Quarto HTML in the current report surface with a
sandboxed same-origin iframe backed by `/api/runs/{run_id}/assets/web_report.html`.
The previous external-link-only behavior is retired. The preview action bar also
offers a one-click image export that captures the same-origin iframe document.

## CSS Design System

The Quarto CSS (`quarto_style.css`) provides:

- Chinese-first local/system font stack: PingFang SC, Microsoft YaHei, Noto Sans SC, system UI.
- Readable centered content width with left TOC.
- Strong Quarto title block with blue/white business-report styling.
- Table styling with sticky headers, row striping, hover state, and readable spacing.
- Callout styling for `.callout-note`, `.callout-tip`, `.callout-important`, `.callout-warning`, `.callout-caution`.
- KPI/card styling for `.kpi-grid` and `.kpi-card`.
- Print-friendly A4 layout.
- Blue/white corporate palette with teal, green, red, amber, and purple accents.

## Failure Behavior

```text
1. Try quarto_renderer.render_quarto_report()
   - quarto not on PATH? -> return None
   - subprocess error? -> return None
   - timeout? -> return None
   - output HTML missing? -> return None

2. write_web_report_artifact() returns None
   - no fallback renderer
   - no Web Report artifact emitted
   - run can still succeed because Web Report is optional
```

## Validation / QA Checklist

When checking a generated Web Report HTML file, verify:

- `<meta name="generator" content="quarto-...">` is present.
- `artifact.data.renderer === "quarto_html"`.
- No duplicate first H1 below the Quarto title block.
- `.callout-important`, `.callout-tip`, or `.callout-warning` blocks appear when the report contains matching sections.
- `.kpi-grid` / `.kpi-card` appear when the report contains small KPI tables.
- Chart links to local `.html` artifacts are replaced by `<iframe src="/api/runs/.../assets/...">`.
- Missing/non-local chart links remain as links.
- Raw `<script>` or raw LLM-authored iframe content from Markdown is not passed through as executable HTML.

## Known Follow-ups

High priority:

1. Keep optimizing Quarto visual quality only; do not revive `delivery_renderer_v2`.
2. Escape iframe `title` attributes with `html.escape(title, quote=True)` to avoid malformed HTML if link text contains quotes.
3. Add visual snapshot / screenshot regression for a representative Quarto report.

Medium priority:

1. If CSS grows further, extract it from `quarto_renderer.py` into a standalone stylesheet template.
2. Explore Quarto PDF/Word/ePub output as optional future artifact formats.
