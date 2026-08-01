"""Quarto CSS themes for the web report renderer.

Provides two selectable visual themes ("business" and "rich_business_report")
via a single `get_quarto_css(style)` lookup function.
"""

from __future__ import annotations

BUSINESS_REPORT_CSS = r"""/* Chinese business-report stylesheet for Quarto HTML output */
/* Data Agent — Quarto renderer — 网页版报告 */

:root {
  --bg: #f4f8fb;
  --paper: #ffffff;
  --ink: #172033;
  --muted: #5b6e8c;
  --line: #d9e4ef;
  --blue: #1769aa;
  --blue-light: #e8f3fb;
  --blue-dark: #0d4a7a;
  --teal: #14a3a3;
  --teal-light: #e6f8f8;
  --green: #168a4a;
  --green-light: #e8f5e9;
  --red: #c43d3d;
  --red-light: #fdf0f0;
  --amber: #b7791f;
  --amber-light: #fef6e6;
  --purple: #7c3aed;
  --purple-light: #f3f0ff;
  --radius: 12px;
  --radius-sm: 8px;
  --shadow-sm: 0 1px 3px rgba(23,32,51,0.06);
  --shadow: 0 4px 12px rgba(23,32,51,0.08);
  --font: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", -apple-system, "Segoe UI", sans-serif;
  --mono: "SF Mono", "Fira Code", "Cascadia Code", monospace;
  --max-width: 960px;
}

/* ── Base ── */
html {
  font-size: 16px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font);
  line-height: 1.78;
  margin: 0;
  padding: 0;
}

/* ── Content wrapper — readable max width ── */
#quarto-content {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 32px 28px 80px;
}

/* ── Title block ── */
#title-block-header {
  background: linear-gradient(160deg, var(--paper) 0%, var(--blue-light) 100%);
  border-radius: 16px;
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  padding: 56px 56px 40px;
  margin-bottom: 36px;
  text-align: center;
}
#title-block-header .title {
  font-size: 32px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.01em;
  line-height: 1.3;
  margin: 0 0 12px;
}
#title-block-header .subtitle {
  font-size: 17px;
  color: var(--muted);
  font-weight: 400;
  margin: 0;
}

/* ── Headings hierarchy ── */
h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--ink);
  margin: 40px 0 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--line);
}
h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
  margin: 36px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
  margin: 24px 0 12px;
}
h4 {
  font-size: 16px;
  font-weight: 600;
  color: var(--muted);
  margin: 20px 0 10px;
}
h5, h6 {
  font-size: 15px;
  font-weight: 600;
  color: var(--muted);
  margin: 16px 0 8px;
}

/* ── Paragraphs ── */
p {
  margin: 0 0 12px;
}

/* ── Strong / emphasis ── */
strong {
  color: var(--ink);
  font-weight: 600;
}

/* ── Links ── */
a {
  color: var(--blue);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}

/* ── Horizontal rules ── */
hr {
  border: none;
  border-top: 1px solid var(--line);
  margin: 28px 0;
}

/* ── Lists ── */
ul, ol {
  margin: 10px 0;
  padding-left: 24px;
}
li {
  margin: 4px 0;
}

/* ── Blockquotes ── */
blockquote {
  border-left: 3px solid var(--blue);
  margin: 16px 0;
  padding: 12px 20px;
  background: var(--blue-light);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink);
}
blockquote p {
  margin: 0;
}

/* ── Code ── */
code {
  font-family: var(--mono);
  font-size: 13px;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--blue-dark);
}
pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 20px 24px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-family: var(--mono);
  font-size: 13px;
  line-height: 1.55;
  margin: 16px 0;
}
pre code {
  background: transparent;
  border: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

/* ── Tables ── */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 16px 0;
  font-size: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
thead {
  background: var(--blue-light);
}
th {
  font-weight: 600;
  color: var(--ink);
  text-align: left;
  padding: 10px 14px;
  border-bottom: 2px solid var(--line);
  white-space: nowrap;
  position: sticky;
  top: 0;
}
td {
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
tbody tr:nth-child(even) {
  background: rgba(244, 248, 251, 0.6);
}
tbody tr:hover {
  background: rgba(232, 243, 251, 0.5);
}

/* ── Table wrapper for horizontal scroll ── */
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 16px 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}

/* ── Callout blocks ── */
.callout-note, .callout-tip, .callout-important, .callout-warning, .callout-caution {
  border-radius: var(--radius-sm);
  padding: 16px 20px;
  margin: 16px 0;
  border: 1px solid;
}
.callout-note {
  background: var(--blue-light);
  border-color: var(--blue);
}
.callout-tip {
  background: var(--green-light);
  border-color: var(--green);
}
.callout-important {
  background: var(--purple-light);
  border-color: var(--purple);
}
.callout-warning {
  background: var(--amber-light);
  border-color: var(--amber);
}
.callout-caution {
  background: var(--red-light);
  border-color: var(--red);
}

/* Callout header */
.callout-note .callout-title,
.callout-tip .callout-title,
.callout-important .callout-title,
.callout-warning .callout-title,
.callout-caution .callout-title {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

/* ── Images ── */
img {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-sm);
}

/* ── Figure captions ── */
figcaption {
  font-size: 13px;
  color: var(--muted);
  text-align: center;
  margin-top: 8px;
}

/* ── Left TOC ── */
#quarto-margin-sidebar {
  background: var(--paper);
  border-right: 1px solid var(--line);
}
#TOC {
  background: transparent;
}
#TOC a {
  color: var(--muted);
  font-size: 13px;
  font-weight: 450;
  text-decoration: none;
  line-height: 1.7;
}
#TOC a:hover {
  color: var(--blue);
}
#TOC .active {
  color: var(--blue);
  font-weight: 600;
}

/* ── Section cards (optional enhancement via custom divs) ── */
.section-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: 32px 40px;
  margin-bottom: 24px;
}

/* ── KPI / metric display ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.kpi-card {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 16px 18px;
  text-align: center;
}
.kpi-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 6px;
}
.kpi-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.2;
}
.kpi-up {
  color: var(--green);
  font-size: 13px;
  font-weight: 600;
}
.kpi-down {
  color: var(--red);
  font-size: 13px;
  font-weight: 600;
}

/* ── Footer ── */
footer {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 20px 28px 48px;
  text-align: center;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}

/* ── Print-friendly ── */
@media print {
  @page {
    margin: 20mm;
    size: A4;
  }
  body {
    background: white;
    font-size: 12px;
    line-height: 1.55;
    color: black;
  }
  #quarto-content {
    max-width: 100%;
    padding: 0;
  }
  #title-block-header {
    background: white;
    box-shadow: none;
    border: none;
    padding: 0 0 20px;
    text-align: left;
  }
  #title-block-header .title {
    font-size: 22px;
    border-bottom: 2px solid black;
    padding-bottom: 6px;
  }
  #TOC, #quarto-margin-sidebar {
    display: none;
  }
  table {
    font-size: 10px;
    page-break-inside: avoid;
  }
  th, td {
    padding: 4px 8px;
  }
  h1 { font-size: 18px; page-break-before: always; }
  h2 { font-size: 16px; }
  h3 { font-size: 14px; }
  pre, blockquote {
    page-break-inside: avoid;
  }
  a {
    color: black;
    text-decoration: underline;
  }
  .kpi-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
"""

RICH_BUSINESS_REPORT_CSS = r"""/* Rich Business Report — deep navy/teal/gold palette */
/* Data Agent — Quarto renderer — rich_business_report theme */

.rich-business-report {
  --rb-bg: #f7f5f1;
  --rb-paper: #ffffff;
  --rb-ink: #1a2332;
  --rb-muted: #6e7687;
  --rb-line: #e0dbd3;
  --rb-navy: #152238;
  --rb-blue: #1e4d8c;
  --rb-teal: #0d9488;
  --rb-teal-light: #e8f7f6;
  --rb-gold: #b8860b;
  --rb-gold-light: #fef9ee;
  --rb-green: #15803d;
  --rb-green-light: #edf7f0;
  --rb-red: #b91c1c;
  --rb-red-light: #fef2f2;
  --rb-radius: 12px;
  --rb-radius-sm: 8px;
  --rb-shadow: 0 2px 12px rgba(26, 35, 50, 0.06);
  --rb-shadow-lg: 0 4px 20px rgba(26, 35, 50, 0.10);
  --rb-font: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", -apple-system, "Segoe UI", sans-serif;
  --rb-mono: "SF Mono", "Fira Code", "Cascadia Code", monospace;

  font-family: var(--rb-font);
  color: var(--rb-ink);
  line-height: 1.78;
}

/* ── Headings ── */
.rich-business-report h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--rb-navy);
  margin: 40px 0 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--rb-teal);
}
.rich-business-report h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--rb-navy);
  margin: 36px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--rb-line);
}
.rich-business-report h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--rb-ink);
  margin: 24px 0 12px;
}
.rich-business-report h4 {
  font-size: 16px;
  font-weight: 600;
  color: var(--rb-muted);
  margin: 20px 0 10px;
}
.rich-business-report h5,
.rich-business-report h6 {
  font-size: 15px;
  font-weight: 600;
  color: var(--rb-muted);
  margin: 16px 0 8px;
}

/* ── Paragraphs ── */
.rich-business-report p {
  margin: 0 0 12px;
}

/* ── Strong ── */
.rich-business-report strong {
  color: var(--rb-ink);
  font-weight: 600;
}

/* ── Links ── */
.rich-business-report a {
  color: var(--rb-blue);
  text-decoration: none;
}
.rich-business-report a:hover {
  text-decoration: underline;
}

/* ── Horizontal rules ── */
.rich-business-report hr {
  border: none;
  border-top: 1px solid var(--rb-line);
  margin: 28px 0;
}

/* ── Lists ── */
.rich-business-report ul,
.rich-business-report ol {
  margin: 10px 0;
  padding-left: 24px;
}
.rich-business-report li {
  margin: 4px 0;
}

/* ── Blockquotes ── */
.rich-business-report blockquote {
  border-left: 3px solid var(--rb-teal);
  margin: 16px 0;
  padding: 12px 20px;
  background: var(--rb-teal-light);
  border-radius: 0 var(--rb-radius-sm) var(--rb-radius-sm) 0;
  color: var(--rb-ink);
}
.rich-business-report blockquote p {
  margin: 0;
}

/* ── Inline code ── */
.rich-business-report :not(pre) > code {
  font-family: var(--rb-mono);
  font-size: 13px;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--rb-line);
  color: var(--rb-navy);
}
.rich-business-report pre {
  background: var(--rb-navy);
  color: #e2e8f0;
  padding: 20px 24px;
  border-radius: var(--rb-radius-sm);
  overflow-x: auto;
  font-family: var(--rb-mono);
  font-size: 13px;
  line-height: 1.55;
  margin: 16px 0;
}
.rich-business-report pre code {
  background: transparent;
  border: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

/* ── Images ── */
.rich-business-report img {
  max-width: 100%;
  height: auto;
  border-radius: var(--rb-radius-sm);
}

/* ── Figure captions ── */
.rich-business-report figcaption {
  font-size: 13px;
  color: var(--rb-muted);
  text-align: center;
  margin-top: 8px;
}

/* ══════════════════════════════════════════════════════════════════════
   Section Panel — white card container for major H2 sections
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .section-panel {
  background: var(--rb-paper);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius);
  box-shadow: var(--rb-shadow);
  padding: 32px 40px;
  margin-bottom: 28px;
}

/* ══════════════════════════════════════════════════════════════════════
   Metric Strip — horizontal grid of KPI cards
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin: 20px 0;
}

.rich-business-report .metric-card {
  background: linear-gradient(180deg, var(--rb-paper) 0%, var(--rb-bg) 100%);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius-sm);
  box-shadow: var(--rb-shadow);
  padding: 20px 22px;
  text-align: center;
}

.rich-business-report .metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--rb-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.rich-business-report .metric-value {
  font-size: 30px;
  font-weight: 700;
  color: var(--rb-navy);
  line-height: 1.2;
}

/* KPI aliases — existing preprocessor outputs .kpi-grid / .kpi-card,
   these map to the rich theme equivalents. */
.rich-business-report .kpi-grid,
.rich-business-report .metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin: 20px 0;
}

.rich-business-report .kpi-card,
.rich-business-report .metric-card {
  background: linear-gradient(180deg, var(--rb-paper) 0%, var(--rb-bg) 100%);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius-sm);
  box-shadow: var(--rb-shadow);
  padding: 20px 22px;
  text-align: center;
}

/* ── Metric colour accents ── */
.rich-business-report .metric-value.up {
  color: var(--rb-green);
}
.rich-business-report .metric-value.down {
  color: var(--rb-red);
}

/* ══════════════════════════════════════════════════════════════════════
   Insight Grid — two-column layout for insight cards
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .insight-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
  margin: 20px 0;
}

.rich-business-report .insight-card {
  background: var(--rb-paper);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius-sm);
  box-shadow: var(--rb-shadow);
  padding: 20px 24px;
}

.rich-business-report .insight-card h3,
.rich-business-report .insight-card h4 {
  margin-top: 0;
  color: var(--rb-navy);
}

/* ══════════════════════════════════════════════════════════════════════
   Risk Card — red left border, light red background
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .risk-card {
  border-left: 4px solid var(--rb-red);
  background: var(--rb-red-light);
  border-radius: 0 var(--rb-radius-sm) var(--rb-radius-sm) 0;
  padding: 16px 20px;
  margin: 16px 0;
}

.rich-business-report .risk-card p {
  margin: 0 0 8px;
}
.rich-business-report .risk-card p:last-child {
  margin-bottom: 0;
}

/* ══════════════════════════════════════════════════════════════════════
   Action Card — teal left border, light teal background
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .action-card {
  border-left: 4px solid var(--rb-teal);
  background: var(--rb-teal-light);
  border-radius: 0 var(--rb-radius-sm) var(--rb-radius-sm) 0;
  padding: 16px 20px;
  margin: 16px 0;
}

.rich-business-report .action-card p {
  margin: 0 0 8px;
}
.rich-business-report .action-card p:last-child {
  margin-bottom: 0;
}

/* ══════════════════════════════════════════════════════════════════════
   Evidence Note — gold left border, light gold background
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .evidence-note {
  border-left: 4px solid var(--rb-gold);
  background: var(--rb-gold-light);
  border-radius: 0 var(--rb-radius-sm) var(--rb-radius-sm) 0;
  padding: 16px 20px;
  margin: 16px 0;
}

.rich-business-report .evidence-note p {
  margin: 0 0 8px;
}
.rich-business-report .evidence-note p:last-child {
  margin-bottom: 0;
}

/* ══════════════════════════════════════════════════════════════════════
   Chart Card — embedded chart container
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .chart-card {
  background: var(--rb-paper);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius);
  box-shadow: var(--rb-shadow);
  padding: 0;
  margin: 24px 0;
  overflow: hidden;
}

.rich-business-report .chart-card iframe {
  display: block;
  width: 100%;
  min-height: 420px;
  border: none;
}

/* ══════════════════════════════════════════════════════════════════════
   Table Card — scrollable wide-table container
   ══════════════════════════════════════════════════════════════════════ */
.rich-business-report .table-card {
  background: var(--rb-paper);
  border: 1px solid var(--rb-line);
  border-radius: var(--rb-radius);
  box-shadow: var(--rb-shadow);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 20px 0;
  padding: 0;
}

/* Compact tables inside table-card — navy header */
.rich-business-report .table-card table {
  margin: 0;
  border: none;
  border-radius: 0;
  font-size: 13px;
  width: 100%;
  border-collapse: collapse;
}

.rich-business-report .table-card thead {
  background: var(--rb-navy);
}

.rich-business-report .table-card th {
  font-weight: 600;
  color: #ffffff;
  text-align: left;
  padding: 10px 14px;
  border-bottom: 2px solid rgba(255, 255, 255, 0.15);
  white-space: nowrap;
}

.rich-business-report .table-card td {
  padding: 8px 14px;
  border-bottom: 1px solid var(--rb-line);
  vertical-align: top;
}

.rich-business-report .table-card tbody tr:nth-child(even) {
  background: rgba(247, 245, 241, 0.5);
}

.rich-business-report .table-card tbody tr:hover {
  background: var(--rb-teal-light);
}

/* ══════════════════════════════════════════════════════════════════════
   Print-friendly — avoid page breaks inside panels
   ══════════════════════════════════════════════════════════════════════ */
@media print {
  @page {
    margin: 20mm;
    size: A4;
  }

  .rich-business-report {
    --rb-bg: #ffffff;
    --rb-paper: #ffffff;
    --rb-ink: #000000;
    --rb-muted: #555555;
    --rb-line: #cccccc;
    --rb-navy: #000000;
    --rb-teal: #0d6b63;
    --rb-gold: #8b6508;

    font-size: 12px;
    line-height: 1.55;
    color: #000000;
  }

  .rich-business-report .section-panel,
  .rich-business-report .risk-card,
  .rich-business-report .action-card,
  .rich-business-report .evidence-note,
  .rich-business-report .chart-card {
    page-break-inside: avoid;
    break-inside: avoid;
    box-shadow: none;
    border-color: var(--rb-line);
  }

  .rich-business-report .metric-card,
  .rich-business-report .insight-card {
    box-shadow: none;
    border-color: var(--rb-line);
  }

  .rich-business-report .table-card table {
    font-size: 10px;
  }

  .rich-business-report .table-card th {
    color: #000000;
    background: #dddddd;
    border-bottom-color: #999999;
  }

  .rich-business-report .table-card th,
  .rich-business-report .table-card td {
    padding: 4px 8px;
  }

  .rich-business-report h1 { font-size: 18px; }
  .rich-business-report h2 { font-size: 16px; }
  .rich-business-report h3 { font-size: 14px; }

  .rich-business-report a {
    color: #000000;
    text-decoration: underline;
  }
}
"""


def get_quarto_css(style: str) -> str:
    """Return the CSS string for the given visual style.

    Args:
        style: One of ``"business"`` or ``"rich_business_report"``.

    Returns:
        CSS string for the requested style.  Unknown styles fall back to
        the ``"business"`` (BUSINESS_REPORT_CSS) theme.
    """
    if style == "rich_business_report":
        return BUSINESS_REPORT_CSS + "\n\n" + RICH_BUSINESS_REPORT_CSS
    return BUSINESS_REPORT_CSS
