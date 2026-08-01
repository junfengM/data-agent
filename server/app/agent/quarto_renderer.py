"""Quarto-based post-Markdown delivery HTML renderer.

Generates a polished Chinese business-report HTML artifact by writing a
temporary .qmd file with YAML front matter and invoking the Quarto CLI.

Quarto is an external CLI dependency — not a Python package.
If Quarto is not installed or rendering fails, this module returns None
without affecting run status.
"""

from __future__ import annotations

import html as _html_mod
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.agent.quarto_runtime import find_quarto_runtime
from app.agent.quarto_styles import get_quarto_css

logger = logging.getLogger(__name__)

_H1_RE = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)

# Callout section heading patterns
_CALLOUT_IMPORTANT_KEYWORDS = re.compile(
    r'执行摘要|诊断结论|诊断报告|综合判断|总体评估'
)
_CALLOUT_TIP_KEYWORDS = re.compile(
    r'已验证的驱动因素|已验证|后续行动|建议的后续|行动建议|优化建议|改进措施'
)
_CALLOUT_WARNING_KEYWORDS = re.compile(
    r'待关注假设|待关注|风险因素|潜在风险|需要注意|待验证'
)


def _extract_title_and_subtitle(
    report_md: str,
    project_name: str | None = None,
) -> tuple[str, str | None]:
    """Extract title from first Markdown H1. project_name becomes subtitle when different."""
    m = _H1_RE.search(report_md)
    h1_title = m.group(1).strip() if m else None

    if h1_title:
        title = h1_title
    elif project_name:
        title = project_name
    else:
        title = "网页版报告"

    subtitle = project_name if (project_name and project_name != title) else None
    return title, subtitle


_PLAIN_CHART_REF_RE = re.compile(r"\[(?P<name>[A-Za-z0-9_.-]+\.html)\](?!\()")


def _linkify_plain_chart_refs(markdown: str, artifacts_dir: Path | None) -> str:
    """Convert plain [chart.html] refs to markdown links so the postprocessor can find them.

    LLMs sometimes emit chart references as bare ``[chart.html]`` instead of
    ``[label](chart.html)``.  This step rewrites them into proper links only
    when the referenced file actually exists in the artifacts directory,
    allowing the downstream ``_postprocess_chart_links`` pass to pick them up.
    """
    known_assets: set[str] = set()
    if artifacts_dir:
        known_assets = {p.name for p in artifacts_dir.glob("*.html")}

    def _repl(match: re.Match) -> str:
        name = match.group("name")
        if known_assets and name not in known_assets:
            return match.group(0)
        return f"[{name}]({name})"

    return _PLAIN_CHART_REF_RE.sub(_repl, markdown)


def _preprocess_report_md(report_md: str, title: str, style: str = "business", artifacts_dir: Path | None = None) -> str:
    """Transform Markdown body for Quarto: strip duplicate H1,
    convert certain sections to callouts, detect KPI tables, preserve chart links.
    When style is "rich_business_report", also apply semantic wrapping
    (chart cards, table cards, risk/action/evidence blocks, section panels).
    """
    md = report_md
    md = _strip_first_h1(md, title)
    md = _escape_hrules(md)
    md = _linkify_plain_chart_refs(md, artifacts_dir)
    md = _convert_section_to_callout(md)
    md = _convert_kpi_tables(md)

    if style == "rich_business_report":
        md = _wrap_chart_links_as_cards(md)
        md = _wrap_large_tables_as_cards(md)
        md = _apply_semantic_wrapping(md)
        md = _wrap_major_sections(md)

    return md


def _strip_first_h1(md: str, title: str) -> str:
    m = _H1_RE.search(md)
    if not m:
        return md
    h1_text = m.group(1).strip()
    h1_end = m.end()
    trailing = md[h1_end:]
    if h1_text == title or title in h1_text or h1_text in title:
        return trailing.lstrip('\n')
    return md


def _escape_hrules(md: str) -> str:
    return re.sub(r'(^|\n)---(\n|$)', r'\1***\2', md)


def _convert_section_to_callout(md: str) -> str:
    """Wrap heading + body pairs with Quarto callout fenced divs."""
    lines = md.splitlines()
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = re.match(r'^(#{2,3})\s+(.+)$', line)
        if hm:
            heading_text = hm.group(2).strip()
            callout = _match_callout_type(heading_text)
            if callout:
                body_lines = []
                j = i + 1
                while j < len(lines):
                    if re.match(r'^(#{1,3})\s+', lines[j]):
                        break
                    body_lines.append(lines[j])
                    j += 1
                body = '\n'.join(body_lines).strip()
                output.append(f'\n:::{{{callout}}}')
                output.append(f'## {heading_text}')
                if body:
                    output.append('')
                    output.append(body)
                output.append(':::')
                i = j
                continue
        output.append(line)
        i += 1
    return '\n'.join(output)


def _match_callout_type(heading: str) -> str | None:
    if _CALLOUT_IMPORTANT_KEYWORDS.search(heading):
        return '.callout-important'
    if _CALLOUT_WARNING_KEYWORDS.search(heading):
        return '.callout-warning'
    if _CALLOUT_TIP_KEYWORDS.search(heading):
        return '.callout-tip'
    return None


def _convert_kpi_tables(md: str) -> str:
    """Detect small key-value tables (≤3 cols, ≤6 rows) and convert to kpi-grid."""
    _FULL_TABLE_RE = re.compile(
        r'\n(\|[^\n]+\|\s*\n'                # header row
        r'\|?\s*:?-{3,}:?\s*'                # separator start
        r'(?:\|\s*:?-{3,}:?\s*)*\|?\s*\n'   # separator rest
        r'((?:\|[^\n]+\|\s*\n)+))',           # body rows
    )

    def _try_convert(m: re.Match) -> str:
        full_block = m.group(1)
        body_text = m.group(2)

        lines = full_block.strip().splitlines()
        if not lines:
            return m.group(0)

        header_cells = _split_table_cells(lines[0])
        col_count = len(header_cells)

        body_rows: list[list[str]] = []
        body_lines = body_text.strip().splitlines()
        for bline in body_lines:
            if re.match(r'^\|?\s*:?-{3,}', bline):
                continue
            cells = _split_table_cells(bline)
            if cells:
                body_rows.append(cells)

        row_count = len(body_rows)
        if not (2 <= col_count <= 3 and 1 <= row_count <= 8):
            return m.group(0)

        kpi_items: list[str] = []
        has_numeric = False
        for row in body_rows:
            if len(row) < 2:
                continue
            label = row[0].strip('*_ ')
            value = row[1].strip('*_ ')
            extra = row[2].strip('*_ ') if len(row) > 2 else ''
            try:
                cleaned = value.strip('*_ ')
                float(cleaned.replace('$', '').replace(',', '').replace(
                    '¥', '').replace('%', '').replace('+', '').replace('-', ''))
                has_numeric = True
            except ValueError:
                pass

            card_lines = [':::{.kpi-card}']
            card_lines.append(f'**{label}**')
            card_lines.append(f'{value}')
            if extra:
                card_lines.append(f'{extra}')
            card_lines.append(':::')
            kpi_items.append('\n'.join(card_lines))

        if not kpi_items or not has_numeric:
            return m.group(0)

        return '\n:::{.kpi-grid}\n' + '\n'.join(kpi_items) + '\n:::\n'

    return _FULL_TABLE_RE.sub(_try_convert, md)


def _split_table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip('|').split('|')]


# ── Rich Business Report preprocessing ────────────────────────────────────────

_CHART_PARAGRAPH_RE = re.compile(
    r'(\[[^\]]+\]\([^)]+\.(?:html|png|jpg|jpeg|svg|webp)\))|'
    r'(📊.*\.(?:html|png|jpg|jpeg|svg|webp))|'
    r'(\.(?:html|png|jpg|jpeg|svg|webp).*📊)',
    re.IGNORECASE,
)

_RISK_KEYWORDS_RE = re.compile(
    r'(风险|注意|异常|波动|缺失|限制|口径|不确定|待验证|样本|不足|偏差)'
)
_ACTION_KEYWORDS_RE = re.compile(
    r'(建议|后续|动作|优化|优先|关注|补充|排查|验证|调整|推进)'
)
_EVIDENCE_KEYWORDS_RE = re.compile(
    r'(数据口径|口径说明|数据来源|统计范围|计算方式|注：|备注：)'
)

_MD_TABLE_HEADER_RE = re.compile(r'^\|.+\|$')
_MD_TABLE_SEP_RE = re.compile(r'^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$')
_MD_TABLE_ROW_RE = re.compile(r'^\|.+\|$')
_MD_H2_RE = re.compile(r'^##\s+.+$')


def _wrap_chart_links_as_cards(md: str) -> str:
    """Wrap paragraphs containing chart links (📊 + .html) in .chart-card divs."""
    lines = md.splitlines()
    blocks = _find_top_level_blocks(lines)
    if not blocks:
        return md

    wraps: list[tuple[int, int]] = []
    for start, end in blocks:
        text = '\n'.join(lines[start:end])
        if _CHART_PARAGRAPH_RE.search(text):
            wraps.append((start, end))

    return _apply_wraps(lines, wraps, '.chart-card')


def _wrap_large_tables_as_cards(md: str) -> str:
    """Wrap wide/deep tables in .table-card divs.

    Triggers when a table has >=4 columns OR >=5 body rows.
    """
    lines = md.splitlines()
    i = 0
    wraps: list[tuple[int, int]] = []

    while i < len(lines):
        stripped = lines[i].strip()
        if not _MD_TABLE_HEADER_RE.match(stripped):
            i += 1
            continue

        if i + 1 >= len(lines):
            i += 1
            continue
        if not _MD_TABLE_SEP_RE.match(lines[i + 1].strip()):
            i += 1
            continue

        header_cells = _split_table_cells(stripped)
        col_count = len(header_cells)
        if col_count < 1:
            i += 1
            continue

        j = i + 2
        body_rows = 0
        while j < len(lines):
            row_stripped = lines[j].strip()
            if _MD_TABLE_ROW_RE.match(row_stripped) and not _MD_TABLE_SEP_RE.match(
                row_stripped
            ):
                body_rows += 1
                j += 1
            else:
                break

        if col_count >= 4 or body_rows >= 5:
            wraps.append((i, j))

        i = j

    return _apply_wraps(lines, wraps, '.table-card')


def _wrap_risk_blocks(md: str) -> str:
    """Wrap paragraphs/lists containing risk keywords in .risk-card divs."""
    return _wrap_semantic_blocks(md, _RISK_KEYWORDS_RE, '.risk-card')


def _wrap_action_blocks(md: str) -> str:
    """Wrap paragraphs/lists containing action keywords in .action-card divs."""
    return _wrap_semantic_blocks(md, _ACTION_KEYWORDS_RE, '.action-card')


def _wrap_evidence_notes(md: str) -> str:
    """Wrap paragraphs containing evidence keywords in .evidence-note divs."""
    return _wrap_semantic_blocks(md, _EVIDENCE_KEYWORDS_RE, '.evidence-note')


_SEMANTIC_CLASSIFIERS: list[tuple[re.Pattern, str]] = [
    (_EVIDENCE_KEYWORDS_RE, '.evidence-note'),
    (_RISK_KEYWORDS_RE, '.risk-card'),
    (_ACTION_KEYWORDS_RE, '.action-card'),
]


def _apply_semantic_wrapping(md: str) -> str:
    """Apply risk/action/evidence wrapping in a single pass. First match wins.

    Evidence > Risk > Action priority. Processes blocks at fenced-div
    depths 0-1 so content inside callouts and kpi-grids is also classified.
    """
    lines = md.splitlines()

    depth_at: list[int] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(':::') and not stripped.startswith('::::'):
            if stripped == ':::':
                depth = max(depth - 1, 0)
            else:
                depth += 1
        depth_at.append(depth)

    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() and depth_at[i] <= 1:
            start = i
            while i < len(lines) and lines[i].strip() and depth_at[i] <= 1:
                i += 1
            blocks.append((start, i))
        else:
            i += 1

    classified: dict[str, list[tuple[int, int]]] = {}
    for start, end in blocks:
        text = '\n'.join(lines[start:end])
        for pattern, class_name in _SEMANTIC_CLASSIFIERS:
            if pattern.search(text):
                classified.setdefault(class_name, []).append((start, end))
                break

    if not classified:
        return md

    all_wraps = [(s, e, c) for c, pairs in classified.items() for s, e in pairs]
    all_wraps.sort(key=lambda x: x[0])

    new_lines: list[str] = []
    cursor = 0
    for start, end, class_name in all_wraps:
        new_lines.extend(lines[cursor:start])
        if new_lines and new_lines[-1] != '':
            new_lines.append('')
        new_lines.append(f':::{{{class_name}}}')
        new_lines.extend(lines[start:end])
        new_lines.append(':::')
        new_lines.append('')
        cursor = end
    new_lines.extend(lines[cursor:])
    return '\n'.join(new_lines)


def _wrap_major_sections(md: str) -> str:
    """Wrap each H2 heading + its body in .section-panel fenced divs.

    Only wraps H2s at fenced-div depth 0 to avoid nesting section-panels
    inside callouts or other structural wrappers.
    """
    lines = md.splitlines()

    depth_at: list[int] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(':::') and not stripped.startswith('::::'):
            if stripped == ':::':
                depth = max(depth - 1, 0)
            else:
                depth += 1
        depth_at.append(depth)

    h2_indices = [
        idx for idx, line in enumerate(lines)
        if _MD_H2_RE.match(line) and depth_at[idx] == 0
    ]

    if not h2_indices:
        return md

    wraps: list[tuple[int, int]] = []
    for idx, h2_idx in enumerate(h2_indices):
        next_h2 = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        wraps.append((h2_idx, next_h2))

    return _apply_wraps(lines, wraps, '.section-panel')


def _wrap_semantic_blocks(md: str, keyword_re: re.Pattern, class_name: str) -> str:
    lines = md.splitlines()
    blocks = _find_top_level_blocks(lines)
    if not blocks:
        return md

    wraps: list[tuple[int, int]] = []
    for start, end in blocks:
        text = '\n'.join(lines[start:end])
        if keyword_re.search(text):
            wraps.append((start, end))

    return _apply_wraps(lines, wraps, class_name)


def _find_top_level_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Find blocks of non-blank lines that are at fenced-div depth 0."""
    depth_at: list[int] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(':::') and not stripped.startswith('::::'):
            if stripped == ':::':
                depth = max(depth - 1, 0)
            else:
                depth += 1
        depth_at.append(depth)

    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() and depth_at[i] == 0:
            start = i
            while i < len(lines) and lines[i].strip() and depth_at[i] == 0:
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def _apply_wraps(
    lines: list[str], wraps: list[tuple[int, int]], class_name: str
) -> str:
    if not wraps:
        return '\n'.join(lines)

    new_lines: list[str] = []
    cursor = 0
    for start, end in wraps:
        new_lines.extend(lines[cursor:start])
        if new_lines and new_lines[-1] != '':
            new_lines.append('')
        new_lines.append(f':::{{{class_name}}}')
        new_lines.extend(lines[start:end])
        new_lines.append(':::')
        new_lines.append('')
        cursor = end
    new_lines.extend(lines[cursor:])
    return '\n'.join(new_lines)


def _postprocess_chart_links(html: str, artifacts_dir: Path | None, run_id: str) -> str:
    if not artifacts_dir or not run_id:
        return html

    from html.parser import HTMLParser
    from urllib.parse import quote

    replacements: list[tuple[str, str]] = []

    class LinkParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            self._depth = getattr(self, '_depth', 0) + 1
            if tag == 'a' and self._depth == 1:
                self._href = dict(attrs).get('href', '')
                self._text_bits = []

        def handle_data(self, data):
            if hasattr(self, '_href'):
                self._text_bits.append(data)

        def handle_endtag(self, tag):
            self._depth = getattr(self, '_depth', 1) - 1
            if tag == 'a' and hasattr(self, '_href') and self._depth == 0:
                href = self._href
                if href.endswith('.html'):
                    chart_name = Path(href).name
                    asset_path = artifacts_dir / chart_name
                    if asset_path.is_file():
                        title = ''.join(self._text_bits).strip()
                        safe_title = _html_mod.escape(title, quote=True)
                        encoded = quote(chart_name, safe='')
                        asset_url = f'/api/runs/{run_id}/assets/{encoded}'
                        iframe = (
                            f'<iframe src="{asset_url}" '
                            f'title="{safe_title}" '
                            f'loading="lazy" '
                            f'style="width:100%;min-height:420px;border:none;border-radius:8px;" '
                            f'sandbox="allow-scripts allow-same-origin">'
                            f'</iframe>'
                        )
                        chunk = html[self._chunk_start:self._chunk_end]
                        replacements.append((chunk, iframe))
                del self._href

    _A_TAG_RE = re.compile(
        r'<a\s+[^>]*href\s*=\s*"[^"]*\.html"[^>]*>.*?</a>', re.DOTALL,
    )

    parser = LinkParser()
    for m in _A_TAG_RE.finditer(html):
        chunk_start, chunk_end = m.start(), m.end()
        parser._depth = 0
        parser._chunk_start = chunk_start
        parser._chunk_end = chunk_end
        parser.feed(html[chunk_start:chunk_end])

    result = html
    for old, new in replacements:
        result = result.replace(old, new, 1)
    return result


def _build_yaml_front_matter(title: str, subtitle: str | None, css_path: Path) -> str:
    """Build safe YAML front matter using yaml.safe_dump."""
    front_matter: dict[str, Any] = {
        "title": title,
        "lang": "zh-CN",
        "from": "markdown-raw_html",
        "format": {
            "html": {
                "toc": True,
                "toc-location": "left",
                "toc-depth": 3,
                "embed-resources": True,
                "css": [css_path.as_posix()],
            }
        },
        "execute": {
            "eval": False,
            "echo": False,
            "warning": False,
        },
    }
    if subtitle:
        front_matter["subtitle"] = subtitle

    return yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False)


def _write_qmd(
    work_dir: Path,
    report_md: str,
    title: str,
    subtitle: str | None,
    css_path: Path,
    style: str = "business",
) -> Path:
    artifacts_parent = work_dir.parent if work_dir.name == "quarto_render" else None
    body = _preprocess_report_md(report_md, title, style, artifacts_dir=artifacts_parent)

    if style == "rich_business_report":
        body = f":::{{.rich-business-report}}\n\n{body}\n\n:::"

    yaml_str = _build_yaml_front_matter(title, subtitle, css_path)
    qmd_content = f"---\n{yaml_str}---\n\n{body}"
    qmd_path = work_dir / "web_report.qmd"
    qmd_path.write_text(qmd_content, encoding="utf-8")
    return qmd_path


def render_quarto_report(
    *,
    report_md: str,
    run_id: str = "",
    project_name: str | None = None,
    artifacts_dir: Path | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Render report_md to polished HTML via Quarto CLI.

    Returns (html, metadata) on success, or None if Quarto is unavailable
    or rendering fails. Never raises — callers treat None as fallback.
    """
    from app.core.settings import get_settings

    settings = get_settings()
    style = settings.quarto_style
    if style not in ("business", "rich_business_report"):
        style = "business"

    runtime = find_quarto_runtime(get_settings())
    if not runtime.available:
        logger.info("quarto_not_found: %s", runtime.message)
        return None

    title, subtitle = _extract_title_and_subtitle(report_md, project_name)

    if artifacts_dir:
        work_dir = artifacts_dir / "quarto_render"
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="quarto_render_"))

    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        css_path = work_dir / "quarto_style.css"
        css_path.write_text(get_quarto_css(style), encoding="utf-8")

        qmd_path = _write_qmd(work_dir, report_md, title, subtitle, css_path, style)

        cmd = [
            str(runtime.path),
            "render",
            str(qmd_path.name),
            "--to", "html",
            "--output", "web_report.html",
            "--quiet",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=get_settings().quarto_render_timeout_seconds,
        )

        if result.returncode != 0:
            logger.warning(
                "quarto_render_failed: exit_code=%d stderr=%s",
                result.returncode,
                result.stderr[:500] if result.stderr else "",
            )
            return None

        output_path = work_dir / "web_report.html"
        if not output_path.is_file():
            logger.warning("quarto_render_missing_output: %s not found", output_path)
            return None

        html = output_path.read_text(encoding="utf-8")

        html = _postprocess_chart_links(html, artifacts_dir, run_id)

        metadata: dict[str, Any] = {
            "renderer": "quarto_html",
            "quarto_available": True,
            "quarto_source": runtime.source,
            "quarto_version": runtime.version,
            "quarto_style": style,
            "title": title,
        }
        if subtitle:
            metadata["subtitle"] = subtitle
        return html, metadata

    except subprocess.TimeoutExpired:
        logger.warning("quarto_render_timeout")
        return None
    except Exception:
        logger.warning("quarto_render_failed", exc_info=True)
        return None
    finally:
        if not artifacts_dir and work_dir.exists():
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass


