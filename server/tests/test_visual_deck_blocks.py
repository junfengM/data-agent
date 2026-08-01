from types import SimpleNamespace

from app.agent.visual_deck_blocks import (
    audit_visual_coverage,
    build_visual_deck_blocks,
    clean_report_line,
    compile_visual_plan,
    inject_visual_deck_blocks,
    parse_markdown_tables,
)
from app.models.schemas import ArtifactBlock, ArtifactBlockType


REPORT_MD = """
# 模块 2：去年 5 月之后趋势与今年后续关注重点

## 核心结论

2025年H2销售额14,486,273元，2026年YTD销售额9,523,786元，整体大盘有所回调。**毛绒玩具是唯一兼具大盘占比(28.3%)与双期增长的绝对机会品类。** 12月单月283.7万，是今年下半年需提前备战的关键窗口。

## A. 2025年6-12月后续月度趋势

| 月份 | 销售额 | 新客数 | 线上占比 |
|------|--------|-------|---------|
| 2025-06 | 2,064,601 | 1,874 | 34.0% |
| 2025-07 | 1,969,338 | 2,604 | 31.0% |
| 2025-12 | 2,836,899 | 1,793 | 43.5% |

## B. 2025年6-12月品类/品牌趋势

| 品类 | H2销售额 | H1销售额 | 增长% |
|------|---------|---------|-------|
| 毛绒玩具 | 4,100,699 | 2,282,019 | +79.7% |
| 保温杯壶 | 1,434,999 | 1,262,313 | +13.7% |
| 配件 | 95,000 | 135,000 | -29.6% |

## D. 今年后续重点关注清单

### 阶段 1：6-8月 → 暑期/出行旺季

**重点关注品类：** 毛绒玩具、旅行收纳、帽饰
**经营动作：** 6月上新暑期毛绒IP → 提前备货 → 毛绒堆头+出行场景陈列 → 小程序出行组合推荐

## 关键风险提示

1. 2026 YTD整体月均较H2下降8.0%——大盘有回调压力
2. 服饰、数码周边等品类从去年H2强转为今年YTD弱，需逐个品牌诊断
"""


def test_parse_markdown_tables_extracts_rows():
    tables = parse_markdown_tables(REPORT_MD)

    assert len(tables) == 2
    assert tables[0].columns == ["月份", "销售额", "新客数", "线上占比"]
    assert tables[0].rows[-1]["月份"] == "2025-12"


def test_build_visual_deck_blocks_creates_management_blocks():
    blocks = build_visual_deck_blocks(title="模块2", report_md=REPORT_MD)
    block_types = [block.type.value for block in blocks]
    titles = [block.title for block in blocks]

    assert "kpi_grid" in block_types
    assert "trend_panel" in block_types
    assert "leaderboard_pair" in block_types
    assert "next_action_list" in block_types
    assert "risk_panel" in block_types
    assert any(title and "核心" in title for title in titles)
    assert len(blocks) <= 32


def test_metric_change_and_stage_timeline_are_derived_without_replacing_text():
    report_md = """
## 渠道趋势

线上占比从34.0%持续攀升至43.5%，店内占比从66.0%降至56.5%。

## 后续行动

### 阶段 1：6-8月

**重点关注品类：** 毛绒玩具、旅行收纳
**经营动作：** 提前备货 → 上新 → 场景陈列

### 阶段 2：9-10月

**重点关注品类：** 数码周边、美容仪
**经营动作：** 礼赠主题陈列 → 小程序推荐
"""
    blocks = build_visual_deck_blocks(title="经营报告", report_md=report_md)

    change = next(block for block in blocks if block.type == ArtifactBlockType.metric_change)
    assert change.source_section == "渠道趋势"
    assert change.items[0]["start"] == "34.0%"
    assert change.items[0]["end"] == "43.5%"
    assert change.items[0]["delta"] == "+9.5个百分点"

    timeline = next(block for block in blocks if block.type == ArtifactBlockType.stage_timeline)
    assert timeline.source_section == "后续行动"
    assert [item["label"] for item in timeline.items] == ["阶段 1：6-8月", "阶段 2：9-10月"]


def test_visual_deck_blocks_are_inserted_after_their_source_section():
    manifest = SimpleNamespace(
        blocks=[
            ArtifactBlock(id="intro", type=ArtifactBlockType.markdown, body="## 核心结论\n\n正文"),
            ArtifactBlock(id="channel", type=ArtifactBlockType.markdown, body="## 渠道趋势\n\n线上占比从34%升至43.5%。"),
            ArtifactBlock(id="risk", type=ArtifactBlockType.markdown, body="## 风险\n\n需要关注。"),
        ],
        tables=[],
        charts=[],
        actions=[],
    )
    derived = [
        ArtifactBlock(
            id="change",
            type=ArtifactBlockType.metric_change,
            title="渠道变化",
            source_section="渠道趋势",
            items=[{"label": "线上占比", "start": "34%", "end": "43.5%"}],
        )
    ]

    inject_visual_deck_blocks(manifest, derived)

    ids = [block.id for block in manifest.blocks]
    assert ids == ["intro", "channel", "change", "risk"]
    assert manifest.blocks[2].section_role == "visual_deck"


def test_visual_deck_supports_non_sales_analysis_scenarios():
    report_md = """
## 核心发现

注册转化率从18.2%提升至26.7%，平均处理时长从14.0分钟降至9.5分钟。

## 实验分组表现

| 实验组 | 转化率 | 留存率 | 样本数 | 判断 |
|------|------|------|------|------|
| 对照组 | 18.2% | 42.0% | 1200 | 基线 |
| 新流程 | 26.7% | 46.5% | 1180 | 转化和留存同时改善 |

## 推进计划

### 阶段 1：小流量验证

**目标：** 验证异常率和客服反馈
**建议动作：** 保持10%流量 → 每日检查告警

### 阶段 2：扩大覆盖

**目标：** 扩大到50%流量
**建议动作：** 完成监控看板 → 分批放量
"""
    blocks = build_visual_deck_blocks(title="产品实验分析", report_md=report_md)
    block_types = {block.type for block in blocks}

    assert ArtifactBlockType.metric_change in block_types
    assert ArtifactBlockType.comparison_grid in block_types
    assert ArtifactBlockType.stage_timeline in block_types

    changes = next(block for block in blocks if block.type == ArtifactBlockType.metric_change)
    assert {item["label"] for item in changes.items} == {"注册转化率", "平均处理时长"}


def test_llm_visual_plan_selects_and_renames_deterministic_candidates():
    candidates = build_visual_deck_blocks(title="经营报告", report_md=REPORT_MD)
    planned = compile_visual_plan(
        [
            {
                "id": "vp_1",
                "block_type": "leaderboard_pair",
                "source_section": "B1. 品类销售额 Top 15",
                "source_ref": "品类",
                "title": "增长品类与回落品类",
                "intent": "突出增长和拖累的两端",
            }
        ],
        candidates,
    )

    assert planned[0].type == ArtifactBlockType.leaderboard_pair
    assert planned[0].title == "增长品类与回落品类"
    assert planned[0].visual_plan_id == "vp_1"
    assert planned[0].visual_intent == "突出增长和拖累的两端"
    assert planned[0].positive


def test_decimal_percentage_is_not_stripped_as_a_numbered_list_prefix():
    assert clean_report_line("- **0.51%空值**（962行）已排除") == "0.51%空值（962行）已排除"


def test_data_quality_percentage_uses_a_compact_label_and_preserves_detail():
    report_md = """
## 数据源与说明

- **0.51%空值**（962行品名/分类/品牌为空）已排除
"""

    blocks = build_visual_deck_blocks(title="报告", report_md=report_md)
    quality = next(block for block in blocks if block.type == ArtifactBlockType.data_quality_panel)

    assert quality.items == [{
        "label": "0.51%空值",
        "value": "0.51%空值（962行品名/分类/品牌为空）已排除",
    }]


def test_explicit_risk_section_does_not_mix_in_other_section_advice():
    report_md = """
# 报告

## 核心结论

建议加码增长品类，并重点观察机会。

## 关键风险提示

1. 大盘月均下降8.0%，存在回调压力
2. 新品占比偏低，规划需前置
"""

    blocks = build_visual_deck_blocks(title="报告", report_md=report_md)
    risk = next(block for block in blocks if block.type == ArtifactBlockType.risk_panel)

    assert [item["text"] for item in risk.items] == [
        "大盘月均下降8.0%，存在回调压力",
        "新品占比偏低，规划需前置",
    ]


def test_core_conclusion_becomes_an_executive_storyboard_and_keeps_source_details():
    report_md = """
# 经营报告

## 核心结论

销售额从120万元下降至98万元，整体存在回调压力。新品渠道增长35%，是当前最明确的机会。下月需要提前完成重点品类备货。

## 详细分析

渠道表现需要继续观察。
"""
    blocks = build_visual_deck_blocks(title="经营报告", report_md=report_md)
    storyboard = next(block for block in blocks if block.type == ArtifactBlockType.executive_storyboard)
    assert storyboard.source_section == "核心结论"
    assert {item["kind"] for item in storyboard.items} >= {"risk", "opportunity", "action"}

    manifest = SimpleNamespace(
        blocks=[
            ArtifactBlock(id="summary", type=ArtifactBlockType.markdown, body="## 核心结论\n\n原始结论。"),
            ArtifactBlock(id="detail", type=ArtifactBlockType.markdown, body="## 详细分析\n\n正文。"),
        ],
        tables=[],
        charts=[],
        actions=[],
    )
    inject_visual_deck_blocks(manifest, [storyboard])
    assert manifest.blocks[0].display_mode == "source_details"
    assert manifest.blocks[1].type == ArtifactBlockType.executive_storyboard


def test_visual_coverage_learns_safe_adaptive_recipes():
    report_md = """
## 核心结论

转化率从18.2%提升至26.7%。风险事件下降12%，建议扩大覆盖。

## 用户反馈

用户普遍认为流程更清晰。高频用户反馈效率明显改善。少量用户仍然担心学习成本。
"""
    blocks = build_visual_deck_blocks(title="产品分析", report_md=report_md)
    coverage, proposals = audit_visual_coverage(report_md, blocks)

    feedback = next(item for item in coverage if item["source_section"] == "用户反馈")
    assert feedback["status"] == "adapted"
    proposal = next(item for item in proposals if item["source_section"] == "用户反馈")
    assert proposal["block_type"] == "adaptive_story"
    assert proposal["variant"] in {"mosaic", "signals", "steps", "split"}


def test_adaptive_recipe_is_reused_on_the_next_report_build():
    report_md = """
## 核心结论

续费率从68%提升至79%，建议扩大高价值客户覆盖。

## 用户反馈

用户普遍认为流程更清晰。高频用户反馈效率明显改善。少量用户仍然担心学习成本。
"""
    first_blocks = build_visual_deck_blocks(title="产品分析", report_md=report_md)
    _, proposals = audit_visual_coverage(report_md, first_blocks)

    second_blocks = build_visual_deck_blocks(
        title="产品分析",
        report_md=report_md,
        visual_recipes=proposals,
    )

    feedback = next(
        block
        for block in second_blocks
        if block.type == ArtifactBlockType.adaptive_story
        and block.source_section == "用户反馈"
    )
    assert feedback.visual_intent.startswith("project_recipe:")


def test_story_extraction_preserves_thousands_separators():
    report_md = """
## 核心结论

全年销售额达到14,486,273元，同比增长56.0%，是当前最明确的增长信号。会员数达到9,523人。
"""
    blocks = build_visual_deck_blocks(title="经营分析", report_md=report_md)
    storyboard = next(block for block in blocks if block.type == ArtifactBlockType.executive_storyboard)

    combined = " ".join(
        str(item.get("headline", "")) + str(item.get("body", ""))
        for item in storyboard.items
    )
    assert "14,486,273元" in combined
