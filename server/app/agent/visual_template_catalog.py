"""Visual template catalog shared by prompts and visual-deck compilation.

The renderer has a finite set of supported visual primitives.  Exposing that
catalog to the LLM helps it structure Markdown and chart_specs so the compiler
can choose richer layouts without guessing or copying a fixed reference design.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualTemplate:
    id: str
    block_type: str
    use_when: str
    input_shape: str
    report_cues: tuple[str, ...]


VISUAL_TEMPLATES: tuple[VisualTemplate, ...] = (
    VisualTemplate(
        id="executive_storyboard",
        block_type="executive_storyboard",
        use_when="an executive summary or core conclusion contains several distinct findings, opportunities, risks, and headline numbers",
        input_shape="items with headline, body, kind, metrics, and optional implication",
        report_cues=("核心结论", "执行摘要", "摘要", "关键结论", "主要发现"),
    ),
    VisualTemplate(
        id="executive_kpi_grid",
        block_type="kpi_grid",
        use_when="headline metrics, period totals, conversion, share, growth, risk counts, or target/actual comparisons need to be seen first",
        input_shape="items with label, value, optional delta/previous/status/tag",
        report_cues=("核心指标", "KPI", "销售额", "增长", "占比", "客单价", "会员", "订单"),
    ),
    VisualTemplate(
        id="answer_first_summary_strip",
        block_type="page_summary",
        use_when="3-5 concise conclusions should frame the page before evidence details",
        input_shape="items with text/summary fields",
        report_cues=("核心结论", "本页结论", "判断", "总结", "结论"),
    ),
    VisualTemplate(
        id="trend_panel",
        block_type="trend_panel",
        use_when="time series, month/week/day progression, before/after movement, or stage-by-stage trend needs compact visual emphasis",
        input_shape="items with label as period and value as metric",
        report_cues=("趋势", "月份", "月度", "周", "日", "同比", "环比", "走势"),
    ),
    VisualTemplate(
        id="metric_change",
        block_type="metric_change",
        use_when="a sentence states that one metric moved from a clear starting value to a clear ending value",
        input_shape="items with label, start, end, optional delta/direction/context",
        report_cues=("从", "升至", "提升到", "攀升至", "降至", "回落至", "个百分点", "→"),
    ),
    VisualTemplate(
        id="composition_panel",
        block_type="composition_panel",
        use_when="mix/share/channel/category structure should be shown as proportions or relative bars",
        input_shape="items with label and value/share/percent",
        report_cues=("占比", "结构", "构成", "渠道", "份额", "mix", "share"),
    ),
    VisualTemplate(
        id="leaderboard_pair",
        block_type="leaderboard_pair",
        use_when="top/bottom, winners/draggers, fastest growth/decline, contributor ranking, or brand/category ranking is important",
        input_shape="positive and negative item arrays, each with label and value/change",
        report_cues=("Top", "Bottom", "增长最快", "走弱", "拖累", "排名", "排行", "贡献"),
    ),
    VisualTemplate(
        id="delta_bridge",
        block_type="delta_bridge",
        use_when="a KPI change should be explained by several drivers or additive contribution factors",
        input_shape="items with label/driver and value/delta/change",
        report_cues=("拆解", "贡献", "驱动", "归因", "差异", "变化原因", "bridge"),
    ),
    VisualTemplate(
        id="decision_matrix",
        block_type="decision_matrix",
        use_when="prioritization, 2x2 evaluation, tradeoff comparison, or option ranking is needed",
        input_shape="items with label/option, value/impact/score, optional risk",
        report_cues=("矩阵", "优先级", "加码", "挽回", "观察", "低优先级", "取舍"),
    ),
    VisualTemplate(
        id="period_action_list",
        block_type="next_action_list",
        use_when="the report contains operating actions, calendarized execution steps, seasonal plays, or follow-up checklist items",
        input_shape="items with text/action fields",
        report_cues=("经营动作", "建议动作", "关注清单", "阶段", "备货", "上新", "陈列", "直播", "推送"),
    ),
    VisualTemplate(
        id="stage_timeline",
        block_type="stage_timeline",
        use_when="several dated phases or operating windows should read as one continuous execution path",
        input_shape="items with label/period, title, summary, and optional actions",
        report_cues=("阶段", "6-8月", "9-10月", "11-12月", "路线图", "时间表", "节奏"),
    ),
    VisualTemplate(
        id="comparison_grid",
        block_type="comparison_grid",
        use_when="a compact table has a small number of rows that should become comparable cards without losing exact values",
        input_shape="items with label, metrics array, and optional note/status",
        report_cues=("对比", "品类", "品牌", "风险组", "机会组", "表现", "诊断"),
    ),
    VisualTemplate(
        id="adaptive_story",
        block_type="adaptive_story",
        use_when="important prose has no specialized chart or component but should become a safe declarative card, signal, split, or step layout",
        input_shape="items with headline, body, metrics, kind; renderer variant is one of mosaic/signals/steps/split",
        report_cues=("发现", "判断", "原因", "影响", "建议", "机会", "风险", "变化"),
    ),
    VisualTemplate(
        id="risk_panel",
        block_type="risk_panel",
        use_when="risks, caveats, weak signals, data limitations, or interpretation warnings should be highly visible",
        input_shape="items with text/risk/value fields and optional intro body",
        report_cues=("风险", "注意", "限制", "口径", "缺失", "空值", "不可持续", "需观察"),
    ),
    VisualTemplate(
        id="data_quality_panel",
        block_type="data_quality_panel",
        use_when="missingness, excluded rows, coverage, refresh window, source quality, or schema issues affect trust",
        input_shape="items with field/label and value/missing/total fields",
        report_cues=("数据源", "说明", "空值", "排除", "覆盖", "刷新", "口径说明", "质量"),
    ),
    VisualTemplate(
        id="forecast_band",
        block_type="forecast_band",
        use_when="forecast, scenario, target range, confidence band, or future expected value appears in the report",
        input_shape="items with label, value/forecast/expected, optional lower/upper",
        report_cues=("预测", "预计", "情景", "区间", "目标", "forecast", "scenario"),
    ),
    VisualTemplate(
        id="insight_banner",
        block_type="insight_banner",
        use_when="one sentence deserves special attention as a core insight or warning between evidence groups",
        input_shape="title plus text/body/summary",
        report_cues=("关键洞察", "提醒", "判断", "结论", "注意"),
    ),
)


def format_visual_template_catalog_for_prompt() -> str:
    """Return a compact catalog suitable for LLM system prompts."""
    lines = [
        "## Available visual report templates",
        "Use these templates as semantic layout hints when writing report_md. The renderer chooses the final layout automatically, but your Markdown should make the intended visual structure clear. Do not force a fixed page count.",
        "",
    ]
    for template in VISUAL_TEMPLATES:
        cues = ", ".join(template.report_cues[:8])
        lines.append(f"- `{template.id}` → `{template.block_type}`: {template.use_when}. Input: {template.input_shape}. Cues: {cues}.")
    lines.extend([
        "",
        "Guidance:",
        "- Prefer a mix of KPI grids, summaries, trend panels, rankings, action lists, and risk panels for management-style reports.",
        "- Use compact Markdown tables when exact values matter; use bullets and bolded judgments when the renderer should create cards.",
        "- File charts are secondary evidence; native chart_specs and Markdown-derived visual templates are the primary surface.",
    ])
    return "\n".join(lines)


def template_ids() -> list[str]:
    return [template.id for template in VISUAL_TEMPLATES]
