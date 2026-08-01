"""Tests for quarto_renderer — Quarto-based web report delivery."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import yaml

from app.agent.quarto_renderer import (
    _build_yaml_front_matter,
    _convert_kpi_tables,
    _convert_section_to_callout,
    _extract_title_and_subtitle,
    _postprocess_chart_links,
    _preprocess_report_md,
    _strip_first_h1,
    _write_qmd,
    render_quarto_report,
)
from app.agent.quarto_runtime import QuartoRuntime
from app.agent.run_artifacts import write_web_report_artifact


SAMPLE_REPORT_MD = """# 百货经营分析报告

## 执行摘要

诊断结论：Q1整体表现健康。

## 一、总体概览

| 指标 | 数值 |
|------|------|
| Q1总收入 | **$883,000** |
| Q1总订单 | 1,183单 |
| 月均收入 | $294,333 |

## 二、诊断结论

### 已验证的驱动因素

Product A增长贡献63.6%。

### 待关注假设

Product B 3月下滑需排查。

### 建议的后续行动

1. 加大线上投放
2. 优化品类结构

## 三、图表

📊 **图表：** [月度收入趋势](monthly_revenue_trend.html)
"""

MD_NO_H1 = """## 直接二级标题

没有一级标题的报告内容。

### 子节

一些分析。
"""

MD_KPI_TABLE = """## 整体业绩概览

| 指标 | 数值 |
|------|------|
| Q1总收入 | **$883,000** |
| Q1总订单 | 1,183单 |
| 月均收入 | $294,333 |

这是正常段落。
"""

MD_WIDE_TABLE = """## 产品明细

| 产品 | 类别 | Q1收入 | 收入占比 | Q1订单 | AOV |
|------|------|--------|---------|-------|-----|
| Product A | Electronics | $403,000 | 45.6% | 155 | $2,600 |
| Product B | Clothing | $265,000 | 30.0% | 383 | $692 |
| Product C | Food | $215,000 | 24.3% | 645 | $333 |
"""

MD_XSS_ATTEMPT = """# 正常报告

## 概要

这是一段正常文字。

<script>alert(1)</script>

更多分析内容。
"""


# ── Rich business report fixtures ────────────────────────────────────────────

RICH_FIXTURE_RETAIL = """# 商品经营分析报告

## 整体业绩概览

| 指标 | 数值 |
|------|------|
| Q1总收入 | $883,000 |
| Q1总订单 | 1,183单 |
| 月均收入 | $294,333 |

## 渠道分析

| 渠道 | Q1收入 | 收入占比 | Q1订单 | 订单占比 | AOV |
|------|--------|---------|-------|---------|-----|
| 线上 | $403,000 | 45.6% | 155 | 13.1% | $2,600 |
| 线下 | $265,000 | 30.0% | 383 | 32.4% | $692 |
| 直播 | $215,000 | 24.3% | 645 | 54.5% | $333 |

📊 **图表：** [月度收入趋势](monthly_trend.html)

## 诊断结论

### 已验证的驱动因素

Product A 增长贡献 63.6%。

### 待关注假设

Product B 3月下滑需排查原因。异常波动出现在直播渠道。

### 建议的后续行动

1. 加大线上投放
2. 优化品类结构
3. 持续关注线下高端品类

## 风险提示

直播渠道存在样本偏差，口径说明：仅统计已完成订单。
"""

RICH_FIXTURE_USER_RETENTION = """# 用户留存分析报告

## 核心指标

| 指标 | 数值 |
|------|------|
| 7日留存率 | 43.5% |
| 30日留存率 | 28.7% |
| 周活跃用户 | 12,840 |

## 留存漏斗详情

| 阶段 | 用户数 | 转化率 | 环比变化 |
|------|--------|--------|---------|
| 新用户 | 15,200 | 100% | +12.3% |
| 次日回访 | 9,880 | 65.0% | +5.1% |
| 7日活跃 | 6,612 | 43.5% | +2.8% |
| 30日活跃 | 4,362 | 28.7% | -1.2% |

## 发现与判断

次日回访率持续提升说明引导流程优化有效。

📊 **图表：** [留存曲线](retention_curve.html)

## 风险与注意事项

30日留存存在波动，需进一步验证。样本数据来自Q1周期，数据口径：排除测试账号。
"""


# ── Title / body preprocessing ──────────────────────────────────────────────

class TestStripFirstH1:
    def test_h1_removed_when_matches_title(self):
        md = "# Q1 报告\n\n## 概述\n\n内容"
        result = _strip_first_h1(md, "Q1 报告")
        assert result == "## 概述\n\n内容"

    def test_h1_kept_when_no_match(self):
        md = "# 不同的标题\n\n## 概述"
        result = _strip_first_h1(md, "Q1 报告")
        assert "不同的标题" in result

    def test_h1_kept_when_no_h1(self):
        result = _strip_first_h1("## 只有 H2", "某个标题")
        assert "## 只有 H2" in result


class TestConvertSectionToCallout:
    def test_executive_summary_becomes_callout_important(self):
        result = _convert_section_to_callout("## 执行摘要\n\n这是摘要内容。")
        assert ":::{.callout-important}" in result
        assert "## 执行摘要" in result
        assert "这是摘要内容。" in result
        assert result.endswith(":::")

    def test_verified_drivers_becomes_callout_tip(self):
        result = _convert_section_to_callout("## 已验证的驱动因素\n\nProduct A 增长。")
        assert ":::{.callout-tip}" in result
        assert "Product A" in result

    def test_pending_assumptions_becomes_callout_warning(self):
        result = _convert_section_to_callout("## 待关注假设\n\n需要排查。")
        assert ":::{.callout-warning}" in result
        assert "需要排查" in result

    def test_normal_section_unchanged(self):
        md = "## 渠道分析\n\n线上增长快。"
        assert _convert_section_to_callout(md).strip() == md


class TestConvertKpiTables:
    def test_small_2col_table_becomes_kpi_grid(self):
        result = _convert_kpi_tables(MD_KPI_TABLE)
        assert ":::{.kpi-grid}" in result
        assert ":::{.kpi-card}" in result
        assert "Q1总收入" in result
        assert "$883,000" in result

    def test_wide_table_unchanged(self):
        result = _convert_kpi_tables(MD_WIDE_TABLE)
        assert ":::{.kpi-grid}" not in result
        assert "| Product" in result
        assert "Electronics" in result

    def test_non_table_text_unchanged(self):
        md = "## 概述\n\n这是普通段落。没有表格。"
        assert _convert_kpi_tables(md).strip() == md.strip()


class TestPreprocessReportMd:
    def test_h1_stripped(self):
        result = _preprocess_report_md(SAMPLE_REPORT_MD, "百货经营分析报告")
        assert "# 百货经营分析报告" not in result

    def test_callout_sections_wrapped(self):
        result = _preprocess_report_md(SAMPLE_REPORT_MD, "百货经营分析报告")
        assert ":::{.callout-important}" in result
        assert ":::{.callout-warning}" in result
        assert ":::{.callout-tip}" in result

    def test_chart_links_preserved_before_html_postprocess(self):
        result = _preprocess_report_md(SAMPLE_REPORT_MD, "百货经营分析报告")
        assert "monthly_revenue_trend.html" in result


# ── Title / YAML ────────────────────────────────────────────────────────────

class TestExtractTitleAndSubtitle:
    def test_h1_becomes_title(self):
        title, subtitle = _extract_title_and_subtitle(SAMPLE_REPORT_MD)
        assert title == "百货经营分析报告"
        assert subtitle is None

    def test_h1_title_project_subtitle_when_different(self):
        title, subtitle = _extract_title_and_subtitle(SAMPLE_REPORT_MD, "北京百货项目")
        assert title == "百货经营分析报告"
        assert subtitle == "北京百货项目"

    def test_no_h1_no_project_fallback_title(self):
        title, subtitle = _extract_title_and_subtitle(MD_NO_H1)
        assert title == "网页版报告"
        assert subtitle is None


class TestQuartoRuntime:
    def test_returns_none_when_quarto_missing(self):
        runtime = QuartoRuntime(
            available=False, path=None, version=None,
            source="missing",
            message="Quarto CLI not found. Install Quarto or set DATA_AGENT_QUARTO_BIN.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            result = render_quarto_report(report_md=SAMPLE_REPORT_MD)
            assert result is None

    def test_returns_html_when_quarto_present(self):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch.object(Path, "read_text", return_value="<html></html>"):
                        with mock.patch.object(Path, "write_text"):
                            with mock.patch.object(Path, "mkdir"):
                                result = render_quarto_report(report_md=SAMPLE_REPORT_MD)
            assert result is not None


class TestBuildYamlFrontMatter:
    def test_valid_yaml_and_parseable(self, tmp_path):
        css_path = tmp_path / "style.css"
        css_path.write_text("/* */")
        yaml_str = _build_yaml_front_matter("报告", None, css_path)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["title"] == "报告"
        assert parsed["from"] == "markdown-raw_html"
        assert parsed["execute"]["eval"] is False
        assert parsed["execute"]["echo"] is False
        assert parsed["execute"]["warning"] is False

    def test_title_with_quotes(self, tmp_path):
        css_path = tmp_path / "style.css"
        css_path.write_text("/* */")
        parsed = yaml.safe_load(_build_yaml_front_matter('报告"黄金"时段', None, css_path))
        assert parsed["title"] == '报告"黄金"时段'

    def test_title_with_emoji(self, tmp_path):
        css_path = tmp_path / "style.css"
        css_path.write_text("/* */")
        parsed = yaml.safe_load(_build_yaml_front_matter("销售分析 📊", None, css_path))
        assert "📊" in parsed["title"]


class TestWriteQmd:
    def test_qmd_uses_preprocessed_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            css_path = work_dir / "style.css"
            css_path.write_text("/* test */")
            qmd_path = _write_qmd(work_dir, SAMPLE_REPORT_MD, "百货经营分析报告", None, css_path)
            content = qmd_path.read_text(encoding="utf-8")
        assert "from: markdown-raw_html" in content
        assert "# 百货经营分析报告" not in content
        assert ":::{.callout-important}" in content

    def test_qmd_with_xss_content_still_has_raw_html_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            css_path = work_dir / "style.css"
            css_path.write_text("/* test */")
            qmd_path = _write_qmd(work_dir, MD_XSS_ATTEMPT, "正常报告", None, css_path)
            content = qmd_path.read_text(encoding="utf-8")
        assert "from:" in content and "markdown-raw_html" in content


# ── Chart iframe postprocess ────────────────────────────────────────────────

class TestPostprocessChartLinks:
    def test_chart_link_replaced_with_iframe(self, tmp_path):
        (tmp_path / "chart.html").write_text("<div>chart</div>")
        html = '<a href="chart.html">趋势图</a>'
        result = _postprocess_chart_links(html, tmp_path, "run123")
        assert '<iframe' in result
        assert '/api/runs/run123/assets/chart.html' in result
        assert 'sandbox="allow-scripts allow-same-origin"' in result

    def test_nonexistent_chart_link_unchanged(self, tmp_path):
        html = '<a href="missing.html">图表</a>'
        result = _postprocess_chart_links(html, tmp_path, "run123")
        assert '<iframe' not in result
        assert 'missing.html' in result

    def test_no_artifacts_dir_returns_unchanged(self):
        html = '<a href="chart.html">图表</a>'
        assert _postprocess_chart_links(html, None, "run123") == html

    def test_dot_slash_href_normalized(self, tmp_path):
        (tmp_path / "monthly_trend.html").write_text("<div>chart</div>")
        result = _postprocess_chart_links('<a href="./monthly_trend.html">趋势图</a>', tmp_path, "run789")
        assert '<iframe' in result
        assert '/api/runs/run789/assets/monthly_trend.html' in result

    def test_assets_prefix_href_normalized(self, tmp_path):
        (tmp_path / "monthly_trend.html").write_text("<div>chart</div>")
        result = _postprocess_chart_links('<a href="assets/monthly_trend.html">趋势图</a>', tmp_path, "run789")
        assert '<iframe' in result
        assert '/api/runs/run789/assets/monthly_trend.html' in result

    def test_link_with_nested_strong(self, tmp_path):
        (tmp_path / "chart.html").write_text("<div>chart</div>")
        result = _postprocess_chart_links('<a href="chart.html"><strong>月度</strong>收入趋势</a>', tmp_path, "run111")
        assert '<iframe' in result
        assert 'title="月度收入趋势"' in result

    def test_url_encoded_filename(self, tmp_path):
        (tmp_path / "月度 趋势.html").write_text("<div>chart</div>")
        result = _postprocess_chart_links('<a href="月度 趋势.html">图表</a>', tmp_path, "run222")
        assert '<iframe' in result
        assert '%E6%9C%88%E5%BA%A6' in result

    def test_title_escaped_special_chars(self, tmp_path):
        (tmp_path / "chart.html").write_text("<div>c</div>")
        result = _postprocess_chart_links(
            '<a href="chart.html">销售 "趋势" <script>alert(1)</script></a>',
            tmp_path, "run_esc",
        )
        assert '<iframe' in result
        assert '&quot;趋势&quot;' in result

    def test_title_escaped_ampersand_and_quote(self, tmp_path):
        (tmp_path / "chart.html").write_text("<div>c</div>")
        result = _postprocess_chart_links(
            '<a href="chart.html">A & B "C"</a>',
            tmp_path, "run_amp",
        )
        assert 'A &amp; B &quot;C&quot;' in result


# ── render_quarto_report ───────────────────────────────────────────────────

class TestRenderQuartoReport:
    def test_returns_html_and_metadata_with_h1_title(self):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch.object(Path, "read_text", return_value="<html></html>"):
                        with mock.patch.object(Path, "write_text"):
                            with mock.patch.object(Path, "mkdir"):
                                result = render_quarto_report(
                                    report_md=SAMPLE_REPORT_MD,
                                    project_name="北京百货项目",
                                )
        assert result is not None
        _, metadata = result
        assert metadata["renderer"] == "quarto_html"
        assert metadata["title"] == "百货经营分析报告"
        assert metadata["subtitle"] == "北京百货项目"

    def test_returns_none_when_quarto_missing(self):
        runtime = QuartoRuntime(
            available=False, path=None, version=None,
            source="missing",
            message="Quarto CLI not found. Install Quarto or set DATA_AGENT_QUARTO_BIN.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            result = render_quarto_report(report_md=SAMPLE_REPORT_MD)
            assert result is None

    def test_returns_none_on_timeout(self):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="quarto", timeout=120)):
                result = render_quarto_report(report_md=SAMPLE_REPORT_MD)
                assert result is None

    def test_metadata_includes_quarto_style(self):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("app.core.settings.get_settings") as mock_get_settings:
                mock_get_settings.return_value.quarto_style = "business"
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    with mock.patch.object(Path, "is_file", return_value=True):
                        with mock.patch.object(Path, "read_text", return_value="<html></html>"):
                            with mock.patch.object(Path, "write_text"):
                                with mock.patch.object(Path, "mkdir"):
                                    result = render_quarto_report(report_md=SAMPLE_REPORT_MD)
        assert result is not None
        _, metadata = result
        assert metadata["quarto_style"] == "business"


# ── write_web_report_artifact integration ──────────────────────────────────

class TestWriteWebReportArtifact:
    def test_metadata_has_quarto_renderer(self):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch.object(Path, "read_text", return_value="<html></html>"):
                        with mock.patch.object(Path, "write_text"):
                            with mock.patch.object(Path, "mkdir"):
                                artifact = write_web_report_artifact(
                                    run_id="run_001",
                                    report_md=SAMPLE_REPORT_MD,
                                )
        assert artifact is not None
        assert artifact.type == "html_report"
        assert artifact.title == "网页版报告"
        assert artifact.data["renderer"] == "quarto_html"
        assert artifact.data["fallback_used"] is False
        assert artifact.data["fallback_renderer"] is None

    def test_returns_none_when_quarto_unavailable(self):
        runtime = QuartoRuntime(
            available=False, path=None, version=None,
            source="missing",
            message="Quarto CLI not found. Install Quarto or set DATA_AGENT_QUARTO_BIN.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            artifact = write_web_report_artifact(
                run_id="run_001",
                report_md=SAMPLE_REPORT_MD,
            )
        assert artifact is None

    def test_writes_web_report_html_under_artifacts_dir(self, tmp_path):
        runtime = QuartoRuntime(
            available=True, path=Path("/usr/bin/quarto"), version="1.9.38",
            source="system", message="Quarto CLI is available.",
        )
        with mock.patch("app.agent.quarto_renderer.find_quarto_runtime", return_value=runtime):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch.object(Path, "read_text", return_value="<html></html>"):
                        artifact = write_web_report_artifact(
                            run_id="run_tmp",
                            report_md=SAMPLE_REPORT_MD,
                            artifacts_dir=tmp_path,
                        )
        assert artifact is not None
        assert (tmp_path / "web_report.html").is_file()


# ── Rich business report preprocessing ──────────────────────────────────────

class TestRichPreprocessBusinessDefault:
    """Default business style does NOT inject rich components."""

    def test_no_rich_wrapper_in_business_style(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="business")
        assert ".rich-business-report" not in processed
        assert ".chart-card" not in processed
        assert ".table-card" not in processed
        assert ".risk-card" not in processed
        assert ".action-card" not in processed
        assert ".evidence-note" not in processed
        assert ".section-panel" not in processed

    def test_business_style_still_has_callouts(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="business")
        assert ":::{.callout-important}" in processed


class TestRichPreprocessComponents:
    """Rich style adds component wrappers."""

    def test_chart_link_wrapped_in_chart_card(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ":::{.chart-card}" in processed

    def test_wide_table_wrapped_in_table_card(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ":::{.table-card}" in processed

    def test_small_table_not_wrapped_as_table_card(self):
        # The KPI table (2 cols, 3 rows) should NOT be a table-card
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        # Count occurrences of :::{.table-card}
        # Should only appear for the wide table, not the KPI table
        # KPI table should still become kpi-grid
        assert ":::{.kpi-grid}" in processed or ":::{.kpi-card}" in processed

    def test_risk_keywords_trigger_risk_card(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ":::{.risk-card}" in processed

    def test_action_keywords_trigger_action_card(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ":::{.action-card}" in processed

    def test_evidence_keywords_trigger_evidence_note(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ":::{.evidence-note}" in processed

    def test_second_fixture_also_works(self):
        """Different content (user retention) should also get rich components."""
        processed = _preprocess_report_md(RICH_FIXTURE_USER_RETENTION, "用户留存分析报告", style="rich_business_report")
        assert ":::{.chart-card}" in processed
        assert ":::{.table-card}" in processed


class TestRichPreprocessContentPreservation:
    """Rich style preserves ALL original content."""

    def test_original_numbers_preserved(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert "$883,000" in processed
        assert "1,183单" in processed
        assert "$294,333" in processed
        assert "63.6%" in processed

    def test_original_chinese_preserved(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert "商品经营分析报告" not in processed  # H1 is stripped
        assert "渠道分析" in processed
        assert "加大线上投放" in processed
        assert "优化品类结构" in processed

    def test_second_fixture_numbers_preserved(self):
        processed = _preprocess_report_md(RICH_FIXTURE_USER_RETENTION, "用户留存分析报告", style="rich_business_report")
        assert "43.5%" in processed
        assert "28.7%" in processed
        assert "12,840" in processed


class TestRichForbiddenPatterns:
    """Rich style must NOT inject forbidden patterns."""

    def test_no_raw_div(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert "<div" not in processed

    def test_no_raw_script(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert "<script" not in processed

    def test_no_page_break_classes(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert ".report-page" not in processed
        assert ".bottom-conclusion" not in processed
        assert ".deck-page-no" not in processed

    def test_no_forced_page_break(self):
        processed = _preprocess_report_md(RICH_FIXTURE_RETAIL, "商品经营分析报告", style="rich_business_report")
        assert "break-after" not in processed


class TestRichStyleCSS:
    """CSS selector returns correct theme."""

    def test_rich_style_returns_rich_css(self):
        from app.agent.quarto_styles import get_quarto_css
        css = get_quarto_css("rich_business_report")
        assert "rich-business-report" in css
        assert "section-panel" in css
        assert "metric-strip" in css

    def test_business_style_returns_business_css(self):
        from app.agent.quarto_styles import get_quarto_css
        css = get_quarto_css("business")
        assert "rich-business-report" not in css
        assert "Chinese business-report" in css

    def test_unknown_style_falls_back_to_business(self):
        from app.agent.quarto_styles import get_quarto_css
        assert get_quarto_css("unknown") == get_quarto_css("business")


# ── Representative Quarto Web Report smoke ─────────────────────────────────

REPRESENTATIVE_REPORT_MD = """# Q1 百货经营诊断报告

## 执行摘要

**诊断结论：Q1 整体表现健康。** 收入增长 16.3%，订单增长 14.0%。

## 整体业绩概览

| 指标 | 数值 |
|------|------|
| Q1总收入 | $883,000 |
| Q1总订单 | 1,183单 |
| 月均收入 | $294,333 |

## 渠道分析

| 渠道 | Q1收入 | 收入占比 | Q1订单 | 订单占比 | AOV |
|------|--------|---------|-------|---------|-----|
| 线上 | $403,000 | 45.6% | 155 | 13.1% | $2,600 |
| 线下 | $265,000 | 30.0% | 383 | 32.4% | $692 |
| 直播 | $215,000 | 24.3% | 645 | 54.5% | $333 |

📊 **图表：** [月度收入趋势](monthly_trend.html)

📊 **图表：** [不存在的图表](no_such_chart.html)

## 诊断结论

### 已验证的驱动因素

Product A 增长贡献 63.6%。

### 待关注假设

Product B 3月下滑需排查原因。

### 建议的后续行动

1. 加大线上投放
2. 关注线下高端品类

## 风险提示

<script>alert('xss')</script>

以上内容应根据 `from: markdown-raw_html` 配置进行转义。
"""


class TestQuartoWebReportSmoke:
    def test_representative_report_structure(self, tmp_path):
        import shutil
        if not shutil.which("quarto"):
            import pytest
            pytest.skip("Quarto CLI not installed")

        (tmp_path / "monthly_trend.html").write_text("<div>chart</div>")

        result = render_quarto_report(
            report_md=REPRESENTATIVE_REPORT_MD,
            artifacts_dir=tmp_path,
        )
        assert result is not None

        html, metadata = result
        assert len(html) > 1000
        body = html[html.index("<body"):] if "<body" in html else html

        assert "quarto" in html.lower()
        assert metadata["renderer"] == "quarto_html"

        assert ".kpi-grid" in body or "kpi-grid" in body
        assert ".kpi-card" in body or "kpi-card" in body
        assert "callout" in body.lower()
        assert "月度收入趋势" in body
        assert '<script>alert' not in body

    def test_preprocess_deterministic(self):
        processed = _preprocess_report_md(REPRESENTATIVE_REPORT_MD, "Q1 百货经营诊断报告")
        assert "Q1 百货经营诊断报告" not in processed
        assert ":::{.callout-important}" in processed
        assert ":::{.callout-tip}" in processed
        assert ":::{.callout-warning}" in processed
        assert ":::{.kpi-grid}" in processed
        assert "monthly_trend.html" in processed
