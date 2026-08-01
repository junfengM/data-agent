"""Visual deck block compiler for management-style visual reports.

This compiler turns an LLM-authored Markdown analysis into richer visual-report
blocks.  It intentionally does not reproduce a fixed reference layout or fixed
page count; it derives visual hierarchy from the report content and the renderer
catalog.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agent.visual_adaptation import SAFE_VARIANTS, match_visual_recipe
from app.agent.visual_template_catalog import VISUAL_TEMPLATES
from app.agent.visual_deck_constants import (
    MAX_DECK_BLOCKS,
    MAX_TABLE_ROWS,
    VISUAL_BLOCK_TYPES,
    _enum_value,
)
from app.agent.visual_deck_markdown import (
    MarkdownTable,
    SECTION_RE,
    CONTENT_SECTION_RE,
    split_sections,
    split_content_sections,
    parse_markdown_tables,
    _is_table_row,
    _parse_table_block,
    _split_table_row,
)
from app.agent.visual_deck_evidence import (
    attach_stable_source_ids,
    dedupe_appendix_visual_evidence,
    _source_hints,
    _match_source_id,
)
from app.models.schemas import ActionItem, ArtifactBlock, ArtifactBlockType
from app.tools.text_utils import strip_inline_markdown

SUBSECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
METRIC_VALUE_RE = re.compile(
    r"[-+]?\d[\d,]*(?:\.\d+)?(?:个百分点|%|万元|万|元|分钟|小时|秒|天|人|户|单|次|个|条|件|台|倍|pp)",
    re.IGNORECASE,
)
CHANGE_TERMS = (
    "提升到", "提升至", "升至", "增长到", "增至", "攀升至",
    "下降到", "下降至", "降至", "回落到", "回落至", "减少到",
    "从", "由", "→",
)
TEMPLATE_CUE_BY_BLOCK = {template.block_type: template.report_cues for template in VISUAL_TEMPLATES}


def build_visual_deck_blocks(
    *,
    title: str,
    report_md: str,
    manifest: Any | None = None,
    snapshot: Any | None = None,
    plan_caveats: list[str] | None = None,
    visual_plan: list[Any] | None = None,
    visual_recipes: list[dict[str, Any]] | None = None,
) -> list[ArtifactBlock]:
    """Build deterministic visual blocks from the final Markdown report."""
    if not report_md.strip():
        return []

    tables = parse_markdown_tables(report_md)
    sections = split_sections(report_md)
    content_sections = split_content_sections(report_md)
    blocks: list[ArtifactBlock] = []

    opening_title, _ = core_or_opening_section(report_md)
    executive_block = build_executive_storyboard(report_md)
    if executive_block:
        blocks.append(executive_block)
    headline_items = extract_headline_metrics(report_md)
    if headline_items:
        blocks.append(_block(
            ArtifactBlockType.kpi_grid,
            title="核心指标速览",
            subtitle="从报告核心结论和关键数字中提取，用于先看结论再读证据。",
            items=headline_items[:8],
            section_role="executive_summary",
            source_section=opening_title,
        ))

    opening_summary = extract_opening_summary(report_md)
    if opening_summary:
        blocks.append(_block(
            ArtifactBlockType.page_summary,
            title="报告主结论",
            items=[{"text": item} for item in opening_summary[:4]],
            section_role="executive_summary",
            source_section=opening_title,
        ))

    blocks.extend(build_metric_change_blocks(content_sections))
    blocks.extend(build_table_driven_blocks(tables))
    blocks.extend(build_stage_timeline_blocks(sections))
    blocks.extend(build_action_blocks(sections))
    blocks.extend(build_priority_blocks(sections))
    blocks.extend(build_forecast_blocks(sections))
    blocks.extend(build_data_quality_blocks(sections))
    blocks.extend(build_insight_blocks(sections))
    blocks.extend(build_risk_blocks(sections, plan_caveats or []))
    blocks.extend(build_section_summary_blocks(sections))

    base_candidates = dedupe_blocks(blocks)
    adaptive_candidates = build_adaptive_story_blocks(
        content_sections,
        visual_recipes or [],
    )
    candidates = dedupe_blocks(base_candidates + adaptive_candidates)
    planned = compile_visual_plan(visual_plan or [], candidates)
    if planned:
        safety_blocks = [
            block for block in base_candidates
            if block.type in {ArtifactBlockType.risk_panel, ArtifactBlockType.data_quality_panel}
            and not any(existing.type == block.type for existing in planned)
        ]
        selected = dedupe_blocks(planned + safety_blocks)
    else:
        selected = list(base_candidates)

    if executive_block and not any(block.type == ArtifactBlockType.executive_storyboard for block in selected):
        selected.insert(0, executive_block)
    selected = add_adaptive_coverage(selected, adaptive_candidates)
    return dedupe_blocks(selected)[:MAX_DECK_BLOCKS]


def compile_visual_plan(
    visual_plan: list[Any],
    candidates: list[ArtifactBlock],
) -> list[ArtifactBlock]:
    """Bind LLM layout intent to deterministic, source-derived candidates."""
    selected: list[ArtifactBlock] = []
    used_ids: set[str] = set()
    for raw in visual_plan[:24]:
        item = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("block_type") or item.get("type") or "")
        source_section = str(item.get("source_section") or item.get("section") or "")
        source_ref = str(item.get("source_ref") or "")
        if not block_type or not source_section:
            continue
        matches = [
            candidate for candidate in candidates
            if candidate.id not in used_ids and _enum_value(candidate.type) == block_type
        ]
        if not matches:
            continue
        ranked = sorted(
            (
                (_visual_plan_match_score(candidate, source_section, source_ref), candidate)
                for candidate in matches
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] <= 0:
            continue
        block = deepcopy(ranked[0][1])
        used_ids.add(ranked[0][1].id)
        if item.get("title"):
            block.title = str(item["title"])
        block.visual_plan_id = str(item.get("id") or "") or None
        block.visual_intent = str(item.get("intent") or "") or None
        block.evidence_priority = str(item.get("priority") or block.evidence_priority)
        options = item.get("options") if isinstance(item.get("options"), dict) else {}
        requested_variant = str(options.get("variant") or "")
        if requested_variant in SAFE_VARIANTS:
            block.variant = requested_variant
        selected.append(block)

    if selected and len(selected) < 3:
        for candidate in candidates:
            if candidate.id in used_ids:
                continue
            selected.append(candidate)
            used_ids.add(candidate.id)
            if len(selected) >= 3:
                break
    return selected


def _visual_plan_match_score(
    candidate: ArtifactBlock,
    source_section: str,
    source_ref: str,
) -> int:
    candidate_section = normalize_section_title(candidate.source_section or "")
    requested_section = normalize_section_title(source_section)
    score = 0
    if candidate_section and candidate_section == requested_section:
        score += 10
    elif candidate_section and (
        candidate_section in requested_section or requested_section in candidate_section
    ):
        score += 5
    candidate_text = normalize_section_title(
        " ".join((candidate.title or "", candidate.subtitle or "", candidate.source_section or ""))
    )
    normalized_ref = normalize_section_title(source_ref)
    if normalized_ref and normalized_ref in candidate_text:
        score += 6
    return score


def inject_visual_deck_blocks(manifest: Any, deck_blocks: list[ArtifactBlock]) -> None:
    """Insert derived visuals next to their source section when possible."""
    if not deck_blocks:
        return
    existing = list(getattr(manifest, "blocks", []) or [])
    if any(str(getattr(block, "section_role", "") or "").startswith("visual_deck") for block in existing):
        return

    _attach_evidence_ids(deck_blocks, manifest)
    _attach_action_ids(deck_blocks, manifest)

    for block in deck_blocks:
        block.section_role = "visual_deck"

    anchored: dict[str, list[ArtifactBlock]] = {}
    unanchored: list[ArtifactBlock] = []
    for block in deck_blocks:
        anchor = normalize_section_title(block.source_section or "")
        if anchor:
            anchored.setdefault(anchor, []).append(block)
        else:
            unanchored.append(block)

    result: list[Any] = []
    inserted_unanchored = False
    inserted_ids: set[str] = set()
    for existing_block in existing:
        result.append(existing_block)
        if _enum_value(getattr(existing_block, "type", "")) != "markdown":
            continue
        if unanchored and not inserted_unanchored:
            result.extend(unanchored)
            inserted_ids.update(block.id for block in unanchored)
            inserted_unanchored = True
        section_title = normalize_section_title(markdown_block_title(str(getattr(existing_block, "body", "") or "")))
        for block in anchored.get(section_title, []):
            if block.type == ArtifactBlockType.executive_storyboard:
                existing_block.display_mode = "source_details"
            result.append(block)
            inserted_ids.add(block.id)

    remaining = [block for block in deck_blocks if block.id not in inserted_ids]
    if remaining:
        appendix_at = next(
            (
                index for index, block in enumerate(result)
                if _enum_value(getattr(block, "type", "")) == "markdown"
                and "附录" in str(getattr(block, "body", "") or "")
            ),
            len(result),
        )
        result[appendix_at:appendix_at] = remaining
    manifest.blocks = result


def extract_headline_metrics(markdown: str) -> list[dict[str, Any]]:
    """Extract only clean executive-level metrics.

    The previous broad pattern could turn list bullets such as '- **9月**：新品占比'
    into malformed KPI labels.  This pass restricts extraction to explicit summary
    sentences and bolded judgments.
    """
    text = core_or_opening_text(markdown)[:2200]
    items: list[dict[str, Any]] = []

    metric_patterns = [
        (r"(20\d{2}年\d{1,2}月销售额|\d{1,2}月销售额)\s*([\d,.]+万)", "销售"),
        (r"(H2销售额|下半年销售额|去年后续销售额)\s*([\d,.]+万)", "销售"),
        (r"(今年1-5月月均|今年月均|YTD月均)\s*([\d,.]+万)", "今年"),
        (r"(老客数|新客数|成交会员数|订单数)\s*[+增长达到为]*\s*([\d,.]+%|[\d,]+人|[\d,]+)", "客群"),
        (r"(线上渠道?占比|线上占比)\D{0,18}([\d.]+%\s*[→-]\s*[\d.]+%|[\d.]+%)", "渠道"),
    ]
    for pattern, tag in metric_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            label = clean_label(match.group(1))
            value = clean_label(match.group(2))
            if not is_good_metric_label(label):
                continue
            item = {"label": label, "value": value, "tag": tag}
            if item not in items:
                items.append(item)
            if len(items) >= 5:
                break
        if len(items) >= 5:
            break

    for bold in BOLD_RE.findall(text):
        clean = clean_label(bold)
        if len(clean) < 8 or len(items) >= 8:
            continue
        if any(token in clean for token in ("唯一", "机会", "风险", "关键", "增长", "下降", "重点", "引擎")):
            items.append({"label": "重点判断", "value": clean, "tag": "判断"})
    return items


def extract_opening_summary(markdown: str) -> list[str]:
    body = core_or_opening_text(markdown)
    candidates: list[str] = []
    for line in body.splitlines():
        clean = clean_report_line(line)
        if not clean or clean.startswith("|"):
            continue
        if re.match(r"^\d+[.、]\s*", clean):
            candidates.append(clean)
            continue
        if len(clean) >= 18 and any(token in clean for token in ("增长", "下降", "机会", "风险", "关键", "需要", "建议", "重点")):
            candidates.append(clean)
    return unique_texts(candidates)[:4]


def build_executive_storyboard(markdown: str) -> ArtifactBlock | None:
    """Turn a dense core conclusion into a compact visual decision storyboard."""
    title, body = core_or_opening_section(markdown)
    if not body or not any(token in title for token in ("核心结论", "执行摘要", "摘要", "结论")):
        return None
    emphasized = build_story_items("\n".join(BOLD_RE.findall(body)), limit=4)
    items = select_story_items(
        dedupe_story_items(emphasized + build_story_items(body, limit=8)),
        limit=4,
    )
    if len(items) < 2:
        return None
    return _block(
        ArtifactBlockType.executive_storyboard,
        title="核心结论速览",
        subtitle="先看结论、关键数字与经营含义；完整原文仍可展开查看。",
        items=items,
        source_section=title,
        source_excerpt=body[:1000],
        variant="executive",
        coverage_id=f"coverage_{_stable_slug(title)}",
    )


def build_adaptive_story_blocks(
    sections: list[tuple[str, str]],
    recipes: list[dict[str, Any]],
) -> list[ArtifactBlock]:
    """Create safe renderer recipes for prose that lacks a specialized visual."""
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        score = section_signal_score(title, body)
        if score < 4 or any(token in title for token in ("数据源", "说明", "附录")):
            continue
        items = build_story_items(body, limit=6)
        if not items:
            # Fallback: split body into paragraphs for high-signal sections
            raw_items = _paragraph_items(body)
            if not raw_items:
                continue
            items = raw_items
        recipe = match_visual_recipe(title, recipes)
        variant = str(recipe.get("variant")) if recipe else infer_story_variant(title, body, items)
        block = _block(
            ArtifactBlockType.adaptive_story,
            title=f"{title}：重点拆解",
            subtitle="该章节尚无专用图表，使用受控的声明式版式增强扫读。",
            items=items,
            source_section=title,
            source_excerpt=body[:1000],
            variant=variant,
            coverage_id=f"coverage_{_stable_slug(title)}",
        )
        if recipe:
            block.visual_intent = f"project_recipe:{recipe['id']}"
        blocks.append(block)
    return blocks


def add_adaptive_coverage(
    selected: list[ArtifactBlock],
    adaptive_candidates: list[ArtifactBlock],
    limit: int = 12,
) -> list[ArtifactBlock]:
    covered = {normalize_section_title(block.source_section or "") for block in selected}
    for block in selected:
        for item in block.items or []:
            child_title = str(item.get("label") or item.get("title") or "")
            if child_title:
                covered.add(normalize_section_title(child_title))
    additions: list[ArtifactBlock] = []
    learned = [
        candidate for candidate in adaptive_candidates
        if str(candidate.visual_intent or "").startswith("project_recipe:")
    ]
    fresh = [candidate for candidate in adaptive_candidates if candidate not in learned]
    for candidate in learned[:8] + fresh:
        section = normalize_section_title(candidate.source_section or "")
        if not section or section in covered:
            continue
        additions.append(candidate)
        covered.add(section)
        fresh_count = sum(
            1 for block in additions
            if not str(block.visual_intent or "").startswith("project_recipe:")
        )
        if fresh_count >= limit:
            break
    return selected + additions


def audit_visual_coverage(
    report_md: str,
    blocks: list[ArtifactBlock],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return section-level coverage and safe project recipe proposals."""
    coverage: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    by_section: dict[str, list[str]] = {}
    for block in blocks:
        section = normalize_section_title(block.source_section or "")
        if section:
            by_section.setdefault(section, []).append(_enum_value(block.type))
        for item in block.items or []:
            child_title = str(item.get("label") or item.get("title") or "")
            if child_title:
                by_section.setdefault(normalize_section_title(child_title), []).append(_enum_value(block.type))
    for title, body in split_content_sections(report_md):
        normalized = normalize_section_title(title)
        score = section_signal_score(title, body)
        block_types = list(dict.fromkeys(by_section.get(normalized, [])))
        if block_types:
            status = "adapted" if set(block_types) == {"adaptive_story"} else "covered"
        else:
            status = "low_signal" if score < 4 else "uncovered"
        item = {
            "id": f"coverage_{_stable_slug(title)}",
            "source_section": title,
            "status": status,
            "signal_score": score,
            "block_types": block_types,
        }
        coverage.append(item)
        if status == "adapted":
            adaptive_block = next(
                (
                    block for block in blocks
                    if normalize_section_title(block.source_section or "") == normalized
                    and block.type == ArtifactBlockType.adaptive_story
                ),
                None,
            )
            variant = (
                adaptive_block.variant
                if adaptive_block and adaptive_block.variant
                else infer_story_variant(title, body, build_story_items(body, limit=6))
            )
            cues = section_recipe_cues(title, body)
            if cues:
                proposals.append({
                    "id": f"recipe_{_stable_slug('|'.join(cues))}",
                    "block_type": "adaptive_story",
                    "variant": variant,
                    "cues": cues,
                    "intent": f"为未覆盖章节《{title}》增加{variant}声明式视觉布局",
                    "learned_from": title,
                    "source_section": title,
                })
    return coverage, proposals


def core_or_opening_text(markdown: str) -> str:
    return core_or_opening_section(markdown)[1]


def core_or_opening_section(markdown: str) -> tuple[str, str]:
    sections = split_sections(markdown)
    for title, body in sections:
        if any(token in title for token in ("核心结论", "执行摘要", "摘要", "结论")):
            return title, body.strip()
    return sections[0] if sections else ("正文", markdown.split("---", 1)[0].strip())


def build_metric_change_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    """Turn explicit from/to statements into deterministic visual comparisons."""
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        items: list[dict[str, Any]] = []
        for sentence in metric_change_clauses(body):
            if not any(term in sentence for term in CHANGE_TERMS):
                continue
            values = METRIC_VALUE_RE.findall(sentence)
            if len(values) < 2:
                continue
            start, end = values[0], values[-1]
            if metric_unit(start) != metric_unit(end):
                continue
            direction = infer_change_direction(sentence, start, end)
            label = metric_change_label(sentence)
            item: dict[str, Any] = {
                "label": label,
                "start": start,
                "end": end,
                "direction": direction,
                "context": sentence[:240],
            }
            delta = metric_delta(start, end)
            if delta:
                item["delta"] = delta
            if item not in items:
                items.append(item)
            if len(items) >= 3:
                break
        if items:
            blocks.append(_block(
                ArtifactBlockType.metric_change,
                title=f"{title}：指标变化",
                subtitle="保留原文判断，并把明确出现的起点和终点转成可扫读变化卡。",
                items=items,
                source_section=title,
                source_excerpt=" ".join(item["context"] for item in items),
            ))
    return blocks[:6]


def build_table_driven_blocks(tables: list[MarkdownTable]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for table in tables:
        columns_text = " ".join(table.columns)
        if any(key in columns_text for key in ("预测", "预计", "上限", "下限", "目标")):
            block = forecast_block_from_table(table)
            if block:
                blocks.append(bind_block_to_section(block, table.title))
            continue
        if any(key in columns_text for key in ("优先级", "风险", "收益", "影响", "象限")):
            block = decision_block_from_table(table)
            if block:
                blocks.append(bind_block_to_section(block, table.title))
            continue
        if "月份" in columns_text and any(key in columns_text for key in ("销售额", "新客", "线上占比", "订单", "客单价")):
            blocks.extend(bind_block_to_section(block, table.title) for block in monthly_trend_blocks(table))
            continue
        if any(key in columns_text for key in ("品类", "品牌", "商品", "渠道", "地区")) and any(key in columns_text for key in ("增长", "变化", "增幅", "贡献", "下降")):
            block = growth_leaderboard_block(table)
            if block:
                blocks.append(bind_block_to_section(block, table.title))
            comparison = comparison_grid_from_table(table)
            if comparison:
                blocks.append(bind_block_to_section(comparison, table.title))
            continue
        if any(key in columns_text for key in ("空值", "缺失", "覆盖", "行数", "排除")):
            block = data_quality_block_from_table(table)
            if block:
                blocks.append(bind_block_to_section(block, table.title))
            continue
        comparison = comparison_grid_from_table(table)
        if comparison:
            blocks.append(bind_block_to_section(comparison, table.title))
    return blocks


def comparison_grid_from_table(table: MarkdownTable) -> ArtifactBlock | None:
    """Promote compact, descriptive tables into reader-friendly comparison cards."""
    if len(table.columns) < 3 or len(table.rows) < 2:
        return None
    note_col = find_column(table.columns, "诊断", "判断", "备注", "意义", "建议", "趋势")
    if len(table.rows) > 8 and not note_col:
        return None
    label_col = find_column(
        table.columns,
        "品类", "品牌", "商品", "渠道", "地区", "月份", "阶段", "项目", "类型",
    ) or table.columns[0]
    metric_cols = [
        column for column in table.columns
        if column not in {label_col, note_col} and any(
            str(row.get(column, "")).strip() for row in table.rows[:8]
        )
    ][:4]
    if len(metric_cols) < 2:
        return None
    items = []
    for row in table.rows[:6]:
        items.append({
            "label": row.get(label_col, "-"),
            "metrics": [
                {"label": column, "value": row.get(column, "-")}
                for column in metric_cols
            ],
            "note": row.get(note_col) if note_col else None,
        })
    return _block(
        ArtifactBlockType.comparison_grid,
        title=f"{table.title}：重点对比",
        subtitle="原表继续保留；这里将关键行和指标转成更适合横向比较的卡片。",
        items=items,
    )


def monthly_trend_blocks(table: MarkdownTable) -> list[ArtifactBlock]:
    rows = table.rows[:MAX_TABLE_ROWS]
    if not rows:
        return []
    month_col = find_column(table.columns, "月份", "month", "日期", "date") or table.columns[0]
    sales_col = find_column(table.columns, "销售额", "sales", "revenue")
    new_col = find_column(table.columns, "新客", "new")
    online_col = find_column(table.columns, "线上占比", "online")
    order_col = find_column(table.columns, "订单", "order")
    aov_col = find_column(table.columns, "客单价", "aov")

    blocks: list[ArtifactBlock] = []
    last_row = rows[-1]
    kpis: list[dict[str, Any]] = []
    for label, col in (("期末销售额", sales_col), ("期末新客", new_col), ("期末线上占比", online_col), ("期末订单数", order_col), ("期末客单价", aov_col)):
        if col and last_row.get(col) not in (None, ""):
            kpis.append({"label": label, "value": last_row.get(col), "tag": str(last_row.get(month_col, "期末"))})
    if kpis:
        blocks.append(_block(ArtifactBlockType.kpi_grid, title="月度关键指标", subtitle=f"基于《{table.title}》末期表现提炼。", items=kpis))

    if sales_col:
        blocks.append(_block(
            ArtifactBlockType.trend_panel,
            title="销售额月度趋势",
            subtitle="用紧凑趋势条展示高低点，便于快速判断经营节奏。",
            items=[{"label": str(row.get(month_col, "-")), "value": row.get(sales_col)} for row in rows],
        ))
    if online_col:
        blocks.append(_block(
            ArtifactBlockType.composition_panel,
            title="线上占比变化",
            subtitle="展示渠道结构向线上迁移或回落的方向。",
            items=[{"label": str(row.get(month_col, "-")), "value": row.get(online_col)} for row in rows],
        ))
    return blocks


def growth_leaderboard_block(table: MarkdownTable) -> ArtifactBlock | None:
    label_col = find_column(table.columns, "品类", "品牌", "商品", "渠道", "地区", "category", "brand", "item") or table.columns[0]
    growth_col = find_column(table.columns, "增长%", "增长", "变化", "增幅", "贡献", "change")
    value_col = growth_col or find_numeric_column(table)
    if not value_col:
        return None
    ranked = []
    for row in table.rows:
        label = row.get(label_col, "-")
        if label in (None, ""):
            continue
        value = row.get(value_col)
        ranked.append({"label": label, "value": value, "numeric": numeric(value)})
    if not ranked:
        return None
    ranked.sort(key=lambda item: item["numeric"], reverse=True)
    positive = [{"label": item["label"], "value": item["value"]} for item in ranked if item["numeric"] >= 0][:6]
    negative = [{"label": item["label"], "value": item["value"]} for item in reversed(ranked) if item["numeric"] < 0][:6]
    if not positive and not negative:
        positive = [{"label": item["label"], "value": item["value"]} for item in ranked[:6]]
    return _block(
        ArtifactBlockType.leaderboard_pair,
        title=f"{table.title}：增长/回落重点",
        subtitle="按报告表格中的增长或变化字段自动排序，保留为经营关注清单。",
        positive=positive,
        negative=negative,
        left_title="增长靠前",
        right_title="回落靠前",
    )


def decision_block_from_table(table: MarkdownTable) -> ArtifactBlock | None:
    label_col = find_column(table.columns, "选项", "方案", "品类", "品牌", "项目", "象限") or table.columns[0]
    impact_col = find_column(table.columns, "影响", "收益", "增长", "机会", "score", "分") or find_numeric_column(table)
    risk_col = find_column(table.columns, "风险", "投入", "难度", "备注")
    items = []
    for row in table.rows[:8]:
        item = {"label": row.get(label_col, "-")}
        if impact_col:
            item["value"] = row.get(impact_col)
        if risk_col:
            item["risk"] = row.get(risk_col)
        items.append(item)
    return _block(ArtifactBlockType.decision_matrix, title=f"{table.title}：优先级判断", subtitle="将表格中的方案、影响和风险压缩为决策卡片。", items=items) if items else None


def forecast_block_from_table(table: MarkdownTable) -> ArtifactBlock | None:
    label_col = find_column(table.columns, "月份", "阶段", "情景", "场景", "日期", "period") or table.columns[0]
    forecast_col = find_column(table.columns, "预测", "预计", "目标", "expected", "forecast") or find_numeric_column(table)
    lower_col = find_column(table.columns, "下限", "lower", "low")
    upper_col = find_column(table.columns, "上限", "upper", "high")
    if not forecast_col:
        return None
    items = []
    for row in table.rows[:10]:
        item = {"label": row.get(label_col, "-"), "value": row.get(forecast_col)}
        if lower_col:
            item["lower"] = row.get(lower_col)
        if upper_col:
            item["upper"] = row.get(upper_col)
        items.append(item)
    return _block(ArtifactBlockType.forecast_band, title=f"{table.title}：预测区间", subtitle="展示未来情景、目标或上下限，不额外创造预测值。", items=items)


def data_quality_block_from_table(table: MarkdownTable) -> ArtifactBlock | None:
    label_col = find_column(table.columns, "字段", "项目", "数据", "来源") or table.columns[0]
    value_col = find_column(table.columns, "空值", "缺失", "覆盖", "行数", "比例", "说明") or find_numeric_column(table)
    if not value_col:
        return None
    return _block(
        ArtifactBlockType.data_quality_panel,
        title=f"{table.title}：数据质量",
        subtitle="将影响可信度的数据质量或覆盖问题集中展示。",
        items=[{"label": row.get(label_col, "-"), "value": row.get(value_col)} for row in table.rows[:10]],
    )


def build_section_summary_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        if len(blocks) >= 5:
            break
        if any(skip in title for skip in ("数据源", "说明", "风险提示")):
            continue
        bullets = extract_high_signal_items(body, limit=4)
        if bullets:
            blocks.append(_block(ArtifactBlockType.page_summary, title=title, subtitle="将该章节的判断压缩成可扫读结论。", items=[{"text": item} for item in bullets], source_section=title))
    return blocks


def build_stage_timeline_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        stages = split_subsections(body)
        stage_like_count = sum(
            1
            for stage_title, _ in stages
            if "阶段" in stage_title or re.search(r"\d{1,2}\s*[-–—]\s*\d{1,2}\s*月", stage_title)
        )
        if len(stages) < 2 or stage_like_count < 2:
            continue
        items: list[dict[str, Any]] = []
        for stage_title, stage_body in stages[:6]:
            actions = extract_actions(stage_body)[:4]
            highlights = extract_labeled_lines(stage_body)
            items.append({
                "label": stage_title,
                "summary": highlights[0] if highlights else first_plain_sentence(stage_body),
                "actions": actions,
                "details": highlights[1:4],
            })
        if items:
            blocks.append(_block(
                ArtifactBlockType.stage_timeline,
                title=f"{title}：执行路线图",
                subtitle="按照原报告中的阶段顺序展示重点对象和经营动作。",
                items=items,
                source_section=title,
            ))
    return blocks[:3]


def build_action_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        if not has_template_cue("next_action_list", title + "\n" + body[:900]):
            continue
        stages = split_subsections(body) or [(title, body)]
        for stage_title, stage_body in stages[:5]:
            actions = extract_actions(stage_body)
            if actions:
                blocks.append(_block(
                    ArtifactBlockType.next_action_list,
                    title=stage_title,
                    subtitle="从报告中的经营动作、建议动作和重点关注项提取。",
                    items=[{"text": action} for action in actions[:7]],
                    source_section=title,
                ))
    return blocks


def build_priority_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        if not has_template_cue("decision_matrix", title + "\n" + body[:1200]):
            continue
        items = []
        for line in body.splitlines():
            clean = clean_report_line(line)
            if not clean or _is_table_row(clean):
                continue
            if any(token in clean for token in ("加码", "挽回", "观察", "低优先级", "优先", "高风险", "机会")):
                label, _, rest = clean.partition("→")
                if not rest:
                    label, _, rest = clean.partition("：")
                items.append({"label": label[:24] or "优先级", "value": rest or clean})
        if items:
            blocks.append(_block(ArtifactBlockType.decision_matrix, title=f"{title}：优先级矩阵", subtitle="根据报告中的优先级、机会和风险描述自动生成决策卡片。", items=items[:8], source_section=title))
    return blocks


def build_forecast_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections:
        if not has_template_cue("forecast_band", title + body[:900]):
            continue
        items = []
        for line in body.splitlines():
            clean = clean_report_line(line)
            if len(clean) >= 8 and not _is_table_row(clean) and any(token in clean for token in ("预测", "预计", "目标", "情景", "区间")):
                items.append({"label": clean[:18], "value": clean})
        if items:
            blocks.append(_block(ArtifactBlockType.forecast_band, title=f"{title}：未来情景", subtitle="将预测、目标或情景描述集中展示，便于后续跟踪。", items=items[:6], source_section=title))
    return blocks


def build_data_quality_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    items: list[dict[str, Any]] = []
    for title, body in sections:
        if not has_template_cue("data_quality_panel", title + body[:1000]):
            continue
        for line in body.splitlines():
            clean = clean_report_line(line)
            if len(clean) < 6 or _is_table_row(clean):
                continue
            if any(token in clean for token in ("数据源", "空值", "排除", "覆盖", "行", "口径", "定义")):
                label, _, value = clean.partition("：")
                if not value:
                    label = clean.split("（", 1)[0]
                    value = clean
                items.append({"label": label[:24] or "数据说明", "value": value or clean})
    if not items:
        return []
    return [_block(ArtifactBlockType.data_quality_panel, title="数据质量与口径", subtitle="集中展示会影响解读的数据来源、定义和覆盖说明。", items=items[:10], source_section=next((title for title, _ in sections if any(token in title for token in ("数据源", "说明", "口径"))), None))]


def build_insight_blocks(sections: list[tuple[str, str]]) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for title, body in sections[:6]:
        bolds = [clean_label(item) for item in BOLD_RE.findall(body)]
        candidate = next((item for item in bolds if len(item) >= 10 and any(token in item for token in ("机会", "风险", "关键", "唯一", "必须", "重点", "引擎"))), "")
        if candidate:
            candidate = strip_inline_markdown(candidate)
            blocks.append(_block(ArtifactBlockType.insight_banner, title=f"{title}：关键洞察", text=candidate, source_section=title, source_excerpt=candidate))
    return blocks[:3]


def build_risk_blocks(sections: list[tuple[str, str]], caveats: list[str]) -> list[ArtifactBlock]:
    risk_items: list[str] = []
    explicit_sections = [
        (title, body)
        for title, body in sections
        if any(token in title for token in ("风险", "Caveat", "限制"))
    ]
    source_sections = explicit_sections or [
        (title, body)
        for title, body in sections
        if has_template_cue("risk_panel", title + "\n" + body[:700])
    ]
    for title, body in source_sections:
        if any(token in title for token in ("风险", "Caveat", "限制")):
            risk_items.extend(
                clean
                for line in body.splitlines()
                if (clean := clean_report_line(line))
                and len(clean) >= 6
                and not _is_table_row(line.strip())
            )
        else:
            risk_items.extend(extract_high_signal_items(body, limit=8))
    risk_items.extend(caveats[:4])
    risk_items = unique_texts(risk_items)[:8]
    if not risk_items:
        return []
    risk_section = source_sections[0][0] if source_sections else None
    return [_block(ArtifactBlockType.risk_panel, title="风险与口径提醒", subtitle="保留会影响经营判断或执行优先级的限制。", items=[{"text": item} for item in risk_items], source_section=risk_section)]


def split_subsections(body: str) -> list[tuple[str, str]]:
    matches = list(SUBSECTION_RE.finditer(body))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result.append((match.group(1).strip(), body[start:end].strip()))
    return result


def extract_actions(body: str) -> list[str]:
    actions: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("|") or raw.startswith("#"):
            continue
        clean = clean_report_line(line)
        if not clean or _looks_like_table_fragment(clean):
            continue
        if any(token in clean for token in TEMPLATE_CUE_BY_BLOCK.get("next_action_list", ())) or any(token in clean for token in ("提前", "备货", "上新", "陈列", "直播", "推荐", "推送", "加码", "挽回", "维护", "提醒", "包装")):
            if "：" in clean:
                prefix, rest = clean.split("：", 1)
                if prefix in {"经营动作", "建议动作", "重点关注品类", "重点关注品牌", "重点关注商品类型"}:
                    chunks = re.split(r"[→；;、，,]", rest)
                    actions.extend(chunk.strip() for chunk in chunks if is_good_action_text(chunk))
                    continue
            if is_good_action_text(clean):
                actions.append(clean)
    return unique_texts([strip_inline_markdown(a) for a in actions])


def extract_high_signal_items(body: str, limit: int = 5) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("#") or raw.startswith("|"):
            continue
        clean = clean_report_line(line)
        if len(clean) < 8 or _looks_like_table_fragment(clean):
            continue
        if any(token in clean for token in ("增长", "下降", "机会", "风险", "建议", "需要", "重点", "关键", "拉动", "支撑", "回落", "加码", "挽回", "观察")):
            items.append(clean)
    if len(items) < limit:
        for bold in BOLD_RE.findall(body):
            clean = clean_label(bold)
            if len(clean) >= 6:
                items.append(clean)
    return unique_texts(items)[:limit]


def _paragraph_items(body: str, limit: int = 4) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    items: list[dict[str, Any]] = []
    for p in paragraphs[:limit]:
        clean = clean_report_line(p)
        if len(clean) < 8:
            continue
        items.append({
            "headline": clean[:80],
            "body": clean,
            "kind": "signal",
            "metrics": [],
        })
    return items


def build_story_items(body: str, limit: int = 6) -> list[dict[str, Any]]:
    units: list[str] = []
    for line in body.splitlines():
        clean = clean_report_line(line)
        if not clean or _is_table_row(line.strip()) or clean.startswith("图表:"):
            continue
        if len(clean) <= 220 and len(re.findall(r"[。！？；]", clean)) <= 1:
            units.append(clean)
        else:
            units.extend(report_sentences(clean))
    if len(units) < 2:
        units.extend(report_sentences(body))

    items: list[dict[str, Any]] = []
    for unit in unique_texts(units):
        if len(unit) < 8:
            continue
        kind = story_kind(unit)
        metrics = METRIC_VALUE_RE.findall(unit)[:3]
        headline = story_headline(unit)
        items.append({
            "headline": headline,
            "body": unit,
            "kind": kind,
            "metrics": metrics,
        })
        if len(items) >= limit:
            break
    return items


def select_story_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_kinds: set[str] = set()
    for item in items:
        kind = str(item.get("kind") or "signal")
        if kind in seen_kinds:
            continue
        selected.append(item)
        seen_kinds.add(kind)
        if len(selected) >= limit:
            return selected
    for item in items:
        if item not in selected:
            selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def dedupe_story_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        body = str(item.get("body") or "").strip()
        key = re.sub(r"[\s。！？；;]+$", "", body)
        key = re.sub(r"\s+", "", key)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def story_kind(text: str) -> str:
    if any(token in text for token in ("风险", "下降", "回调", "走弱", "偏低", "拖累", "存疑")):
        return "risk"
    if any(token in text for token in ("建议", "需要", "应", "提前", "加码", "备战", "动作")):
        return "action"
    if any(token in text for token in ("机会", "增长", "提升", "爆发", "高峰", "唯一")):
        return "opportunity"
    return "signal"


def story_headline(text: str) -> str:
    clean = clean_label(text)
    protected = re.sub(r"(?<=\d),(?=\d)", "§", clean)
    clauses = [clause.replace("§", ",") for clause in re.split(r"[：:，。；;——]|(?<!\d),(?!\d)", protected)]
    meaningful = next((clause.strip() for clause in clauses if len(clause.strip()) >= 6), clean)
    if len(meaningful) <= 32:
        return meaningful
    return meaningful[:31].rstrip() + "…"


def section_signal_score(title: str, body: str) -> int:
    text = f"{title}\n{body}"
    score = min(len(METRIC_VALUE_RE.findall(text)), 3)
    score += min(len(BOLD_RE.findall(body)), 2)
    score += min(len(report_sentences(body)), 3)
    if any(token in text for token in ("结论", "发现", "反馈", "增长", "下降", "风险", "机会", "建议", "原因", "影响")):
        score += 2
    if "|" in body:
        score -= 2
    return max(score, 0)


def infer_story_variant(title: str, body: str, items: list[dict[str, Any]]) -> str:
    if len(re.findall(r"^\s*\d+[.、]", body, flags=re.MULTILINE)) >= 2 or "阶段" in title:
        return "steps"
    kinds = {str(item.get("kind") or "") for item in items}
    if "risk" in kinds and "opportunity" in kinds:
        return "signals"
    if any(token in title for token in ("对比", "变化", "前后", "原因", "归因")):
        return "split"
    return "mosaic"


def section_recipe_cues(title: str, body: str) -> list[str]:
    cues = [clean_label(title)]
    for token in ("结论", "趋势", "对比", "风险", "机会", "原因", "建议", "阶段", "渠道", "品牌", "品类"):
        if token in title or token in body[:500]:
            cues.append(token)
    return unique_texts(cues)[:6]


def _stable_slug(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return digest


def report_sentences(body: str) -> list[str]:
    lines = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "|", "```")):
            continue
        lines.append(clean_report_line(stripped))
    return [
        sentence.strip()
        for sentence in re.split(r"[。！？；]\s*|\n+", "\n".join(lines))
        if len(sentence.strip()) >= 8
    ]


def metric_change_clauses(body: str) -> list[str]:
    """Split parallel change statements without breaking comma-grouped numbers."""
    clauses: list[str] = []
    for sentence in report_sentences(body):
        protected = re.sub(r"(?<=\d),(?=\d)", "§", sentence)
        clauses.extend(
            clause.replace("§", ",").strip()
            for clause in re.split(r"[，]|(?<!\d),(?!\d)", protected)
            if len(clause.strip()) >= 8
        )
    return clauses


def metric_unit(value: str) -> str:
    match = re.search(
        r"(个百分点|万元|%|万|元|分钟|小时|秒|天|人|户|单|次|个|条|件|台|倍|pp)$",
        value,
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else ""


def metric_number(value: str) -> float | None:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def metric_delta(start: str, end: str) -> str | None:
    start_number = metric_number(start)
    end_number = metric_number(end)
    if start_number is None or end_number is None:
        return None
    delta = end_number - start_number
    unit = metric_unit(end)
    suffix = "个百分点" if unit in {"%", "个百分点", "pp"} else unit
    decimals = 1 if any("." in value for value in (start, end)) else 0
    return f"{delta:+.{decimals}f}{suffix}"


def infer_change_direction(sentence: str, start: str, end: str) -> str:
    if any(term in sentence for term in ("下降", "降至", "回落", "减少", "下滑")):
        return "down"
    if any(term in sentence for term in ("提升", "升至", "增长", "增至", "攀升")):
        return "up"
    start_number = metric_number(start)
    end_number = metric_number(end)
    if start_number is None or end_number is None or start_number == end_number:
        return "flat"
    return "up" if end_number > start_number else "down"


def metric_change_label(sentence: str) -> str:
    clean = clean_report_line(sentence)
    for delimiter in ("从", "由"):
        if delimiter in clean:
            prefix = clean.split(delimiter, 1)[0].strip("：:，, ")
            if prefix:
                return prefix[-28:]
    value_match = METRIC_VALUE_RE.search(clean)
    if value_match:
        prefix = clean[:value_match.start()].strip("：:，, ")
        if prefix:
            return prefix[-28:]
    return clean[:28]


def extract_labeled_lines(body: str) -> list[str]:
    result: list[str] = []
    for raw in body.splitlines():
        clean = clean_report_line(raw)
        if not clean or _is_table_row(raw.strip()):
            continue
        if "：" in clean and any(
            token in clean
            for token in ("重点关注", "商品类型", "经营动作", "建议动作", "目标", "品类", "品牌")
        ):
            result.append(clean)
    return unique_texts(result)


def first_plain_sentence(body: str) -> str:
    sentences = report_sentences(body)
    return sentences[0][:180] if sentences else ""


def bind_block_to_section(block: ArtifactBlock, section: str) -> ArtifactBlock:
    block.source_section = block.source_section or section
    return block


def markdown_block_title(body: str) -> str:
    match = re.search(r"^#{1,4}\s+(.+?)\s*$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def normalize_section_title(title: str) -> str:
    clean = clean_label(title).lower()
    clean = re.sub(r"^[a-z0-9一二三四五六七八九十]+[.、]\s*", "", clean)
    return re.sub(r"\s+", "", clean)


def _attach_evidence_ids(blocks: list[ArtifactBlock], manifest: Any) -> None:
    evidence_items = list(getattr(manifest, "tables", []) or []) + list(getattr(manifest, "charts", []) or [])
    if not evidence_items:
        return
    section_evidence: dict[str, list[str]] = {}
    for manifest_block in list(getattr(manifest, "blocks", []) or []):
        if _enum_value(getattr(manifest_block, "type", "")) != "markdown":
            continue
        section = normalize_section_title(markdown_block_title(str(getattr(manifest_block, "body", "") or "")))
        evidence_ids = [str(value) for value in (getattr(manifest_block, "evidence_ids", []) or []) if value]
        if section and evidence_ids:
            section_evidence[section] = evidence_ids
    for block in blocks:
        if block.evidence_ids:
            continue
        source_evidence = section_evidence.get(normalize_section_title(block.source_section or ""), [])
        if source_evidence:
            block.evidence_ids = source_evidence[:3]
            continue
        text = " ".join([block.title or "", block.subtitle or "", block.text or "", " ".join(str(item) for item in (block.items or [])[:3])])
        matched = []
        for item in evidence_items:
            item_id = str(getattr(item, "id", "") or "")
            item_title = str(getattr(item, "title", "") or "")
            if item_id and item_title and any(token and token in text for token in _tokens(item_title)):
                matched.append(item_id)
        if matched:
            block.evidence_ids = matched[:2]


def _attach_action_ids(blocks: list[ArtifactBlock], manifest: Any) -> None:
    existing_actions = list(getattr(manifest, "actions", []) or [])
    for block in blocks:
        if _enum_value(block.type) != "next_action_list":
            continue
        ids: list[str] = []
        for item in block.items or []:
            text = str(item.get("text") or item.get("action") or item.get("label") or "").strip()
            if not text:
                continue
            action = _match_action(existing_actions, text)
            if action is None:
                action = ActionItem(text=text[:280], priority="medium", evidence_ids=list(block.evidence_ids or []))
                existing_actions.append(action)
            ids.append(action.id)
        block.action_ids = list(dict.fromkeys(ids))
    if existing_actions:
        manifest.actions = existing_actions


def _match_action(actions: list[Any], text: str) -> Any | None:
    text_tokens = set(_tokens(text))
    if not text_tokens:
        return None
    best = None
    best_score = 0
    for action in actions:
        action_text = str(getattr(action, "text", "") or "")
        score = len(text_tokens & set(_tokens(action_text)))
        if score > best_score:
            best = action
            best_score = score
    return best if best_score >= 2 else None


def has_template_cue(block_type: str, text: str) -> bool:
    cues = TEMPLATE_CUE_BY_BLOCK.get(block_type, ())
    lowered = text.lower()
    return any(cue.lower() in lowered for cue in cues)


def clean_report_line(line: str) -> str:
    clean = strip_markdown(line).strip(" -•\t")
    clean = re.sub(r"^\d+(?:、|[.](?!\d))\s*", "", clean)
    return " ".join(clean.split())


def clean_label(text: str) -> str:
    return " ".join(strip_markdown(text).strip(" -•\t:：").split())


def is_good_metric_label(label: str) -> bool:
    if not label or len(label) > 28:
        return False
    return not any(ch in label for ch in "|*#\n") and not label.startswith("-")


def is_good_action_text(text: str) -> bool:
    clean = clean_label(text)
    if len(clean) < 4:
        return False
    if _looks_like_table_fragment(clean):
        return False
    return True


def _looks_like_table_fragment(text: str) -> bool:
    return text.startswith("|") or text.count("|") >= 2 or set(text) <= {"-", "|", " ", ":"}


def find_column(columns: list[str], *needles: str) -> str | None:
    for needle in needles:
        lower = needle.lower()
        for column in columns:
            if lower in column.lower():
                return column
    return None


def find_numeric_column(table: MarkdownTable) -> str | None:
    for column in table.columns:
        values = [numeric(row.get(column)) for row in table.rows[:8]]
        if any(value != 0 for value in values):
            return column
    return None


def numeric(value: Any) -> float:
    raw = str(value or "").replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        return 0.0
    number = float(match.group(0))
    if "万" in raw:
        return number * 10000
    return number


def strip_markdown(text: str) -> str:
    clean = re.sub(r"`([^`]+)`", r"\1", str(text))
    clean = clean.replace("**", "").replace("__", "")
    clean = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", clean)
    return clean.strip()


def unique_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = " ".join(str(item).split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def dedupe_blocks(blocks: list[ArtifactBlock]) -> list[ArtifactBlock]:
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[ArtifactBlock] = []
    for block in blocks:
        key = (
            _enum_value(block.type),
            block.title or "",
            block.source_section or "",
            block.renderer_target or "",
            "|".join(sorted(block.evidence_ids or [])),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(block)
    return result


def _block(block_type: ArtifactBlockType, **kwargs: Any) -> ArtifactBlock:
    return ArtifactBlock(
        id=_block_id(),
        type=block_type,
        evidence_priority=kwargs.pop("evidence_priority", "primary"),
        renderer_target="md_visual",
        block_origin="visual_deck",
        **kwargs,
    )


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", str(text)) if len(token) >= 2]


def _block_id() -> str:
    return f"block_{uuid4().hex[:8]}"
