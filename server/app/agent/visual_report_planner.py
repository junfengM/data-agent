"""Deterministic visual-report planning helpers.

This layer turns existing manifest evidence (cards, tables, charts and report text)
into management-ready visual blocks. It is intentionally conservative: it does
not invent claims, it only restructures already available evidence into richer
visual reading surfaces.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.agent.visual_deck_blocks import normalize_section_title
from app.models.schemas import ArtifactBlock, ArtifactBlockType, ManifestCard, ManifestChart, ManifestTable


def compose_reading_flow(
    narrative_blocks: list[ArtifactBlock],
    md_visual_blocks: list[ArtifactBlock],
    evidence_component_blocks: list[ArtifactBlock],
    appendix_blocks: list[ArtifactBlock],
) -> list[ArtifactBlock]:
    """Unified reading-flow composer for the two-layer visual report architecture.

    Ordering rules:
    1. For each source section: narrative → md_visual → evidence_component
    2. Unanchored md_visual blocks go after the executive summary section
    3. Unanchored evidence_component blocks go to appendix
    4. All appendix blocks go at the end
    """
    section_order: list[str] = []
    section_blocks: dict[str, list[ArtifactBlock]] = {}

    def _section_key(block: ArtifactBlock) -> str:
        section = (block.source_section or "").strip()
        if not section and block.type == ArtifactBlockType.markdown:
            body = (block.body or "").strip()
            match = re.match(r"^#{1,3}\s+(.+?)$", body, re.MULTILINE)
            if match:
                section = match.group(1).strip()
        return normalize_section_title(section)

    # Collect narrative sections in order
    for block in narrative_blocks:
        section = _section_key(block)
        if section not in section_blocks:
            section_blocks[section] = []
            section_order.append(section)
        section_blocks[section].append(block)

    # Place md_visual blocks next to their source section
    unanchored_visual: list[ArtifactBlock] = []
    for block in md_visual_blocks:
        section = _section_key(block) or block.source_section or ""
        if section and section in section_blocks:
            section_blocks[section].append(block)
        else:
            unanchored_visual.append(block)

    # Place evidence_component blocks next to their source section (if anchored),
    # otherwise append to an "unmatched evidence" section
    unmatched_evidence: list[ArtifactBlock] = []
    for block in evidence_component_blocks:
        section = normalize_section_title(block.source_section or "")
        if section and section in section_blocks:
            section_blocks[section].append(block)
        else:
            unmatched_evidence.append(block)

    # Build final order
    result: list[ArtifactBlock] = []
    inserted_unanchored = False

    # Executive summary markers (insert unanchored visuals after these)
    summary_markers = ("执行摘要", "核心结论", "executive summary", "summary")

    for section in section_order:
        result.extend(section_blocks[section])
        if not inserted_unanchored and unanchored_visual:
            section_normalized = normalize_section_title(section)
            if any(normalize_section_title(marker) in section_normalized for marker in summary_markers):
                result.extend(unanchored_visual)
                inserted_unanchored = True

    # Any remaining unanchored visual blocks go before unmatched evidence
    if not inserted_unanchored and unanchored_visual:
        # Insert after the first markdown section
        insert_at = 0
        for i, block in enumerate(result):
            if block.type == ArtifactBlockType.markdown:
                insert_at = i + 1
                break
        result[insert_at:insert_at] = unanchored_visual

    # Unmatched evidence → appendix territory
    appendix_blocks = list(appendix_blocks) + unmatched_evidence

    # Ensure appendix has a header if there are appendix items
    if appendix_blocks and not any(
        "附录" in str(getattr(b, "body", "") or "")
        for b in appendix_blocks
    ):
        result.append(ArtifactBlock(
            id=f"appendix_header_{uuid4().hex[:8]}",
            type=ArtifactBlockType.markdown,
            body="## 附录：补充图表与数据表\n\n以下材料未放入主报告正文，用于补充审阅。",
            evidence_priority="appendix",
            renderer_target="appendix",
            block_origin="reading_flow",
        ))

    result.extend(appendix_blocks)
    return result


VISUAL_REPORT_KEYWORDS = (
    "经营", "概览", "月报", "复盘", "管理层", "看板", "业绩", "销售", "业务",
    "executive", "management", "business", "recap", "overview", "performance",
)


CHART_INTENT_TERMS = {
    "trend": ("趋势", "走势", "环比", "同比", "trend", "time", "month", "week", "date"),
    "comparison": ("对比", "比较", "排名", "排行", "top", "bottom", "comparison", "ranking"),
    "composition": ("结构", "占比", "构成", "composition", "share", "mix", "ratio"),
    "decomposition": ("贡献", "拆解", "差异", "decomposition", "contribution", "bridge", "waterfall"),
    "relationship": ("关系", "相关", "relationship", "correlation", "scatter"),
    "distribution": ("分布", "distribution", "histogram", "box"),
    "funnel": ("漏斗", "转化", "funnel", "conversion"),
    "forecast": ("预测", "预计", "forecast", "scenario"),
}


def should_plan_visual_report(title: str, report_md: str) -> bool:
    """Return True when a report should receive a visual-first layout."""
    text = f"{title}\n{report_md}".lower()
    return any(keyword.lower() in text for keyword in VISUAL_REPORT_KEYWORDS)


def build_visual_report_blocks(
    *,
    title: str,
    report_md: str,
    cards: list[ManifestCard],
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
    plan_caveats: list[str] | None = None,
    charts: list[ManifestChart] | None = None,
    used_chart_ids: set[str] | None = None,
) -> list[ArtifactBlock]:
    """Build optional visual blocks from evidence relationships.

    The planner does not impose a fixed business-report template. It promotes
    LLM-produced chart intent first, then uses table/data-shape heuristics only
    as a fallback when the evidence supports that relationship.
    """
    if not should_plan_visual_report(title, report_md):
        return []

    blocks: list[ArtifactBlock] = []
    kpi_items = _kpi_items_from_cards(cards, datasets)
    if kpi_items:
        blocks.append(ArtifactBlock(
            id=_block_id(),
            type=ArtifactBlockType.kpi_grid,
            title="核心指标速览",
            subtitle="根据语义层指标和可用证据自动生成，便于管理层快速判断整体表现。",
            items=kpi_items[:8],
            evidence_ids=[card.id for card in cards],
        ))

    blocks.extend(_chart_blocks_from_manifest(report_md, charts or [], used_chart_ids or set()))

    for builder in (
        _trend_panel_from_tables,
        _forecast_band_from_tables,
        _delta_bridge_from_tables,
        _relationship_visual_from_tables,
        _risk_panel_from_tables,
        _data_quality_panel_from_tables,
        _decision_matrix_from_report,
    ):
        block = builder(report_md, tables, datasets)
        if block is not None:
            blocks.append(block)

    if plan_caveats:
        blocks.append(ArtifactBlock(
            id=_block_id(),
            type=ArtifactBlockType.risk_panel,
            title="口径与限制",
            subtitle="来自分析计划或验证过程的 caveat。",
            items=[{"label": f"限制 {idx + 1}", "value": caveat} for idx, caveat in enumerate(plan_caveats[:5])],
        ))

    for block in blocks:
        block.renderer_target = "evidence_component"
        block.block_origin = "visual_report_planner"

    return _dedupe_visual_blocks(blocks)


def merge_visual_blocks_into_reading_flow(
    blocks: list[ArtifactBlock],
    visual_blocks: list[ArtifactBlock],
) -> list[ArtifactBlock]:
    """Place visual summaries after the executive summary, not before the report."""
    if not visual_blocks:
        return blocks
    summary_markers = ("执行摘要", "核心结论", "executive summary", "summary")
    insert_at = 0
    first_markdown_index: int | None = None
    for index, block in enumerate(blocks):
        if block.type != ArtifactBlockType.markdown:
            continue
        if first_markdown_index is None:
            first_markdown_index = index
        body = (block.body or "").lower()
        if any(marker in body for marker in summary_markers):
            insert_at = index + 1
            break
    else:
        insert_at = (first_markdown_index + 1) if first_markdown_index is not None else 0
    return blocks[:insert_at] + visual_blocks + blocks[insert_at:]


def _chart_blocks_from_manifest(
    report_md: str,
    charts: list[ManifestChart],
    used_chart_ids: set[str],
) -> list[ArtifactBlock]:
    if not charts:
        return []
    scored: list[tuple[int, ManifestChart]] = []
    for chart in charts:
        if chart.id in used_chart_ids:
            continue
        score = _chart_relevance_score(report_md, chart)
        if score > 0:
            scored.append((score, chart))
    if not scored:
        scored = [(1, chart) for chart in charts if chart.id not in used_chart_ids and (chart.intent or chart.description)][:2]
    selected = [chart for _, chart in sorted(scored, key=lambda item: item[0], reverse=True)[:3]]
    return [
        ArtifactBlock(
            id=_block_id(),
            type=ArtifactBlockType.chart,
            chart_id=chart.id,
            evidence_ids=[chart.id],
            evidence_priority="primary",
        )
        for chart in selected
    ]


def _chart_relevance_score(report_md: str, chart: ManifestChart) -> int:
    text = report_md.lower()
    haystack = " ".join(
        str(part or "")
        for part in (chart.title, chart.subtitle, chart.description, chart.intent, chart.type)
    ).lower()
    score = 0
    if chart.title and chart.title.lower() in text:
        score += 8
    if chart.intent:
        score += 3
    if chart.description:
        score += 1
    score += len(set(haystack.replace("_", " ").split()) & set(text.replace("_", " ").split()))
    for intent, terms in CHART_INTENT_TERMS.items():
        if intent in haystack and any(term in text for term in terms):
            score += 4
        elif any(term in haystack for term in terms) and any(term in text for term in terms):
            score += 2
    return score


def _trend_panel_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    if not any(term in report_text for term in ("趋势", "trend", "走势", "环比", "同比", "month", "week", "date")):
        return None
    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows or len(rows) < 2:
            continue
        time_field = _field_matching(fields, ("date", "month", "week", "time", "日期", "月份", "周"), rows, exclude=set())
        value_field = _first_numeric_field(rows, fields, exclude={time_field} if time_field else set())
        if time_field and value_field:
            items = [
                {"label": str(row.get(time_field, "-")), "value": row.get(value_field)}
                for row in rows[:12]
                if isinstance(row, dict) and _number(row.get(value_field)) is not None
            ]
            if len(items) >= 2:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.trend_panel,
                    title="趋势变化",
                    subtitle=f"按 {time_field} 展示 {value_field} 的变化。",
                    items=items,
                    evidence_ids=[table.id],
                )
    return None


def _forecast_band_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    if not any(term in report_text for term in ("预测", "forecast", "预计", "scenario", "情景")):
        return None
    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows:
            continue
        label_field = (_first_text_field(rows, fields) or fields[0]) if fields else None
        forecast_field = _field_matching(fields, ("forecast", "predict", "expected", "预测", "预计"), rows, exclude={label_field} if label_field else set())
        lower_field = _field_matching(fields, ("lower", "low", "下限"), rows, exclude={label_field} if label_field else set())
        upper_field = _field_matching(fields, ("upper", "high", "上限"), rows, exclude={label_field} if label_field else set())
        if label_field and forecast_field:
            items = []
            for row in rows[:8]:
                if not isinstance(row, dict):
                    continue
                item = {"label": str(row.get(label_field, "-")), "value": row.get(forecast_field)}
                if lower_field:
                    item["lower"] = row.get(lower_field)
                if upper_field:
                    item["upper"] = row.get(upper_field)
                items.append(item)
            if items:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.forecast_band,
                    title="预测区间",
                    subtitle="仅基于已有预测字段展示，不额外生成预测值。",
                    items=items,
                    evidence_ids=[table.id],
                )
    return None


def _delta_bridge_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    if not any(term in report_text for term in ("贡献", "bridge", "waterfall", "拆解", "差异", "variance")):
        return None
    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows:
            continue
        label_field = _first_text_field(rows, fields) or fields[0]
        contribution_field = _field_matching(fields, ("contribution", "delta", "variance", "change", "贡献", "差异", "变化"), rows, exclude={label_field})
        if contribution_field:
            items = _items_for_field(rows, label_field, contribution_field)
            items.sort(key=lambda item: abs(float(item["_numeric"])), reverse=True)
            clean = [{k: v for k, v in item.items() if k != "_numeric"} for item in items[:8]]
            if clean:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.delta_bridge,
                    title="差异贡献拆解",
                    subtitle="按已有贡献/差异字段展示主要驱动项。",
                    items=clean,
                    evidence_ids=[table.id],
                )
    return None


def _relationship_visual_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    ranking_requested = any(term in report_text for term in (
        "贡献", "排名", "排行", "领先", "拖累", "top", "bottom", "rank", "contribution",
    ))
    share_terms = ("share", "pct", "percent", "ratio", "占比", "比例")
    movement_terms = ("delta", "change", "growth", "variance", "lift", "同比", "环比", "变化", "增量")

    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows or not fields:
            continue
        label_field = _first_text_field(rows, fields) or fields[0]
        share_field = _field_matching(fields, share_terms, rows, exclude={label_field})
        movement_field = _field_matching(fields, movement_terms, rows, exclude={label_field})

        if share_field:
            items = _items_for_field(rows, label_field, share_field)
            if items:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.composition_panel,
                    title="结构分布",
                    subtitle="按当前分析口径展示各项占比。",
                    items=_clean_items(items[:8]),
                    evidence_ids=[table.id],
                )

        value_field = movement_field
        if value_field or ranking_requested:
            value_field = value_field or _first_numeric_field(rows, fields, exclude={label_field})
            if not value_field:
                continue
            items = _items_for_field(rows, label_field, value_field)
            positive = [item for item in items if float(item["_numeric"]) >= 0]
            negative = [item for item in items if float(item["_numeric"]) < 0]
            positive.sort(key=lambda item: abs(float(item["_numeric"])), reverse=True)
            negative.sort(key=lambda item: abs(float(item["_numeric"])), reverse=True)
            if positive or negative:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.leaderboard_pair,
                    title="变化与重点项",
                    subtitle="仅在证据支持排序或正负变化时展示。",
                    left_title="正向 / 重点项",
                    right_title="负向 / 拖累项",
                    positive=_clean_items(positive[:6]),
                    negative=_clean_items(negative[:6]),
                    evidence_ids=[table.id],
                )
    return None


def _risk_panel_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    risk_requested = any(term in report_text for term in ("风险", "risk", "异常", "告警", "缺口", "下降", "拖累"))
    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows or not fields:
            continue
        label_field = _first_text_field(rows, fields) or fields[0]
        risk_field = _field_matching(fields, ("risk", "score", "gap", "decline", "风险", "缺口", "下降", "异常"), rows, exclude={label_field})
        if risk_field:
            items = _items_for_field(rows, label_field, risk_field)
            items.sort(key=lambda item: abs(float(item["_numeric"])), reverse=True)
            if items:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.risk_panel,
                    title="风险与异常",
                    subtitle="按已有风险/缺口/异常字段展示优先关注项。",
                    items=_clean_items(items[:6]),
                    evidence_ids=[table.id],
                )
        if risk_requested:
            numeric_field = _first_numeric_field(rows, fields, exclude={label_field})
            if numeric_field:
                items = [item for item in _items_for_field(rows, label_field, numeric_field) if float(item["_numeric"]) < 0]
                items.sort(key=lambda item: abs(float(item["_numeric"])), reverse=True)
                if items:
                    return ArtifactBlock(
                        id=_block_id(),
                        type=ArtifactBlockType.risk_panel,
                        title="风险与异常",
                        subtitle="报告提到风险，且证据中存在负向数值项。",
                        items=_clean_items(items[:6]),
                        evidence_ids=[table.id],
                    )
    return None


def _data_quality_panel_from_tables(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    if not any(term in report_text for term in ("数据质量", "缺失", "口径", "quality", "missing", "null")):
        return None
    for table in tables:
        rows = datasets.get(table.dataset) or []
        if not rows:
            continue
        fields = [column.field for column in table.columns]
        items: list[dict[str, Any]] = []
        for field in fields[:10]:
            total = sum(1 for row in rows if isinstance(row, dict))
            missing = sum(1 for row in rows if isinstance(row, dict) and row.get(field) in (None, ""))
            if missing:
                items.append({"label": field, "value": missing, "total": total, "direction": "down"})
        if items:
            return ArtifactBlock(
                id=_block_id(),
                type=ArtifactBlockType.data_quality_panel,
                title="数据质量提示",
                subtitle="基于当前预览数据检测到缺失项，仅作为审阅提示。",
                items=items,
                evidence_ids=[table.id],
            )
    return None


def _decision_matrix_from_report(
    report_md: str,
    tables: list[ManifestTable],
    datasets: dict[str, list[dict[str, Any]]],
) -> ArtifactBlock | None:
    report_text = report_md.lower()
    if not any(term in report_text for term in ("方案", "选择", "决策", "option", "decision", "matrix")):
        return None
    for table in tables:
        rows = datasets.get(table.dataset) or []
        fields = [column.field for column in table.columns]
        if not rows or not fields:
            continue
        option_field = _first_text_field(rows, fields) or fields[0]
        score_field = _field_matching(fields, ("score", "impact", "priority", "收益", "影响", "优先级"), rows, exclude={option_field})
        risk_field = _field_matching(fields, ("risk", "effort", "cost", "风险", "成本", "投入"), rows, exclude={option_field})
        if score_field:
            items: list[dict[str, Any]] = []
            for row in rows[:8]:
                if not isinstance(row, dict):
                    continue
                items.append({
                    "label": str(row.get(option_field, "-")),
                    "value": row.get(score_field),
                    "risk": row.get(risk_field) if risk_field else None,
                })
            if items:
                return ArtifactBlock(
                    id=_block_id(),
                    type=ArtifactBlockType.decision_matrix,
                    title="决策矩阵",
                    subtitle="仅基于已有方案评分/影响字段展示。",
                    items=items,
                    evidence_ids=[table.id],
                )
    return None


def _field_matching(
    fields: list[str],
    terms: tuple[str, ...],
    rows: list[dict[str, Any]],
    *,
    exclude: set[str | None],
) -> str | None:
    for field in fields:
        if field in exclude:
            continue
        normalized = field.lower()
        if any(term in normalized for term in terms) and any(
            _number(row.get(field)) is not None or isinstance(row.get(field), str)
            for row in rows if isinstance(row, dict)
        ):
            return field
    return None


def _items_for_field(
    rows: list[dict[str, Any]],
    label_field: str,
    value_field: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        numeric_value = _number(row.get(value_field))
        if numeric_value is None:
            continue
        items.append({
            "label": str(row.get(label_field, "-")),
            "value": row.get(value_field, numeric_value),
            "direction": "up" if numeric_value >= 0 else "down",
            "_numeric": numeric_value,
        })
    return items


def _clean_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in item.items() if k != "_numeric"} for item in items]


def _kpi_items_from_cards(cards: list[ManifestCard], datasets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for card in cards:
        row = (datasets.get(card.dataset) or [{}])[0]
        for metric in card.metrics:
            value = row.get(metric.field, "-") if isinstance(row, dict) else "-"
            item = {
                "label": metric.label,
                "value": value,
            }
            if metric.caveat:
                item["caveat"] = metric.caveat
            items.append(item)
    return items


def _first_text_field(rows: list[dict[str, Any]], fields: list[str]) -> str | None:
    for field in fields:
        if any(isinstance(row.get(field), str) and row.get(field) for row in rows if isinstance(row, dict)):
            return field
    return None


def _first_numeric_field(rows: list[dict[str, Any]], fields: list[str], *, exclude: set[str | None] | None = None) -> str | None:
    excluded = exclude or set()
    for field in fields:
        if field in excluded:
            continue
        if any(_number(row.get(field)) is not None for row in rows if isinstance(row, dict)):
            return field
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return parsed


def _dedupe_visual_blocks(blocks: list[ArtifactBlock]) -> list[ArtifactBlock]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[ArtifactBlock] = []
    for block in blocks:
        key = (str(block.type), tuple(block.evidence_ids))
        if key in seen:
            continue
        seen.add(key)
        result.append(block)
    return result


def _first_useful_sentence(markdown: str) -> str:
    lines = [line.strip(" #-*\t") for line in markdown.splitlines()]
    for line in lines:
        if len(line) < 12:
            continue
        if line.lower().startswith(("table", "chart", "source", "数据来源")):
            continue
        if "|" in line and "---" in line:
            continue
        return line[:180]
    return ""


def _summary_items_from_markdown(markdown: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in markdown.splitlines():
        clean = line.strip()
        if not clean.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ")):
            continue
        text = clean.lstrip("-*0123456789. ").strip()
        if len(text) >= 8:
            items.append({"text": text[:160]})
    return items


def _block_id() -> str:
    return f"block_{uuid4().hex[:8]}"
