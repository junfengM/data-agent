from __future__ import annotations

import re
from typing import Any

from app.tools.semantic_validation import validate_semantic_ambiguity
from app.tools.validation_types import ValidationResult
from app.agent.visual_deck_constants import VISUAL_BLOCK_TYPES
from app.agent.trace_diagnostics import check_report_sanity, count_report_features
from app.models.schemas import BLOCK_ORIGINS, RENDERER_TARGETS

_CARD_CANDIDATE_RE = re.compile(r"(?<![\d.])(?:\d[ -]?){13,19}(?![\d.])")

# Product code field names — numbers near these should not be flagged as phone
_PRODUCT_CODE_FIELDS = frozenset({
    "hg_code", "sku", "SKU", "商品编码", "商品ID", "货号",
    "条码", "barcode", "product_code", "item_code", "会员卡号",
    "订单号", "order_id", "order_no", "运单号", "tracking_no",
})

# Phone context keywords — plain digit sequences are only flagged if near these
_PHONE_CONTEXT_KEYWORDS = frozenset({
    "phone", "tel", "mobile", "电话", "手机号", "联系方式",
    "联系电话", "手机", "fax", "传真",
})

# Phone number regex with explicit formatting (parentheses, hyphens, dots)
_PHONE_FORMATTED_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.]?)?\([0-9]{3}\)\s*[-.]?\s*[0-9]{3}\s*[-.]?\s*[0-9]{4}\b"
    r"|"
    r"(?<!\d)(?:\+?1[-.]?)?[0-9]{3}[-.][0-9]{3}[-.][0-9]{4}\b"
)

# Plain 10-11 digit sequence (only flagged with phone context nearby)
_PHONE_PLAIN_RE = re.compile(r"\b[0-9]{10,11}\b")


def _passes_luhn(value: str) -> bool:
    """Return True if the digit sequence passes the Luhn checksum."""
    digits = [int(ch) for ch in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def validate_markdown_content_sanity(
    report_md: str | None,
    chart_specs: list | None = None,
    has_chart_evidence: bool = False,
    has_table_evidence: bool = False,
) -> ValidationResult:
    """Validate that report_md is not contaminated by code/DSML and integrates evidence."""
    features = count_report_features(report_md or "")
    sanity = check_report_sanity(
        report_md or "",
        chart_specs=chart_specs,
        chart_ref_count=features["chart_ref_count"],
        evidence_ref_count=features["evidence_ref_count"],
        has_evidence=has_chart_evidence or has_table_evidence,
    )

    if not sanity["report_sanity_passed"]:
        reason = sanity["failure_reason"]
        if reason == "report_content_contaminated_by_tool_call_or_code":
            return ValidationResult(
                gate_id="markdown_report_content_sanity",
                passed=False,
                message=f"Report content contains code/DSML fragments: {', '.join(sanity['report_md_bad_markers'][:5])}",
                severity="fail",
                details={
                    "bad_markers": sanity["report_md_bad_markers"],
                    "code_marker_count": sanity["report_md_code_marker_count"],
                },
                fix_hint="Remove all code, DSML tags, function calls, and tool-call syntax from report_md.",
                owner_layer="planner",
            )
        elif reason == "evidence_not_integrated":
            return ValidationResult(
                gate_id="markdown_report_content_sanity",
                passed=False,
                message="Evidence was generated but report contains no chart refs, evidence refs, or chart_specs.",
                severity="warning",
                details={
                    "has_chart_evidence": has_chart_evidence,
                    "has_table_evidence": has_table_evidence,
                },
                fix_hint="Include chart names, table references, and evidence citations in report_md. Add chart_specs for every chart.",
                owner_layer="planner",
            )

    return ValidationResult(
        gate_id="markdown_report_content_sanity",
        passed=True,
        message="Report content sanity check passed.",
        severity="info",
    )


EVIDENCE_BACKED_VISUAL_TYPES = frozenset({
    "executive_storyboard",
    "adaptive_story",
    "kpi_grid",
    "delta_bridge",
    "leaderboard_pair",
    "trend_panel",
    "composition_panel",
    "risk_panel",
    "decision_matrix",
    "data_quality_panel",
    "forecast_band",
    "metric_change",
    "comparison_grid",
})

CORE_CONCLUSION_TOKENS = (
    "执行摘要",
    "核心结论",
    "结论",
    "摘要",
    "summary",
    "executive",
    "recommendation",
    "建议",
    "finding",
    "key finding",
)

NON_TABLE_VISUAL_TYPES = VISUAL_BLOCK_TYPES | {"chart", "metric-strip"}


def _is_visual_report(delivery_mode: str | None) -> bool:
    return delivery_mode == "visual_report"


def _block_text(block: dict) -> str:
    parts = [
        block.get("title"),
        block.get("subtitle"),
        block.get("body"),
        block.get("content"),
        block.get("text"),
        block.get("summary"),
        block.get("data"),
    ]
    return "\n".join(str(part) for part in parts if part is not None)


def validate_evidence_coverage(step_results: list[dict], report_md: str) -> ValidationResult:
    if not step_results:
        return ValidationResult(
            gate_id="evidence_coverage",
            passed=False,
            severity="fail",
            message="No analysis steps were executed",
        )
    tables: list[dict] = []
    charts: list[dict] = []
    for result in step_results:
        tables.extend(result.get("tables", []))
        charts.extend(result.get("charts", []))
    has_evidence = bool(tables or charts)
    return ValidationResult(
        gate_id="evidence_coverage",
        passed=has_evidence,
        severity="pass" if has_evidence else "fail",
        message=f"Found {len(tables)} table(s) and {len(charts)} chart(s) as evidence",
        details={"tables": len(tables), "charts": len(charts)},
    )


def validate_markdown_content_preservation(
    report_md: str,
    blocks: list[dict],
) -> ValidationResult:
    """Require the designed report to retain every substantive Markdown line."""
    source_lines = [
        normalized
        for line in report_md.splitlines()
        if (normalized := _normalize_markdown_line(line))
    ]
    rendered_text = "\n".join(
        str(block.get("body") or "")
        for block in blocks
        if block.get("type") in {"markdown", "prose"}
    )
    normalized_rendered = "\n".join(
        normalized
        for line in rendered_text.splitlines()
        if (normalized := _normalize_markdown_line(line))
    )
    missing = [line for line in source_lines if line not in normalized_rendered]
    unique_missing = list(dict.fromkeys(missing))
    passed = not unique_missing
    return ValidationResult(
        gate_id="markdown_content_preservation",
        passed=passed,
        severity="pass" if passed else "fail",
        message=(
            f"All {len(source_lines)} substantive Markdown line(s) are preserved"
            if passed
            else f"{len(unique_missing)} substantive Markdown line(s) are missing from the visual reading flow"
        ),
        details={"missing_lines": unique_missing[:20], "source_line_count": len(source_lines)},
        fix_hint=(
            None if passed
            else "Check compose_reading_flow() and merge_visual_blocks_into_reading_flow() "
                 "in visual_report_planner.py: ensure every source Markdown line has a "
                 "corresponding block. Missing lines may indicate visual deck blocks "
                 "dropped content or header normalization mismatched."
        ),
        owner_layer="reading_flow",
        related_block_ids=[],
        can_auto_repair=False,
    )


def validate_visual_section_coverage(
    report_md: str,
    blocks: list[dict],
) -> ValidationResult:
    """Audit whether high-signal prose sections received visual treatment."""
    from app.agent.visual_deck_blocks import audit_visual_coverage
    from app.models.schemas import ArtifactBlock

    visual_blocks = []
    for raw in blocks:
        try:
            visual_blocks.append(ArtifactBlock.model_validate(raw))
        except Exception:
            continue
    coverage, proposals = audit_visual_coverage(report_md, visual_blocks)
    uncovered = [item for item in coverage if item.get("status") == "uncovered"]
    adapted = [item for item in coverage if item.get("status") == "adapted"]
    passed = len(uncovered) <= 2
    return ValidationResult(
        gate_id="visual_section_coverage",
        passed=passed,
        severity="pass" if not uncovered else "warning",
        message=(
            f"Visual coverage OK: {len(adapted)} section(s) use adaptive layouts"
            if not uncovered
            else f"{len(uncovered)} high-signal section(s) remain visually uncovered"
        ),
        details={
            "uncovered_sections": [item.get("source_section") for item in uncovered[:10]],
            "adaptive_sections": len(adapted),
            "recipe_proposals": len(proposals),
        },
        fix_hint=(
            None if not uncovered
            else "Consider adding candidate_angles or visual_plan items targeting these "
                 "sections. Alternatively, review audit_visual_coverage() thresholds. "
                 "Uncovered sections may need explicit visual_plan items from the Planner."
        ),
        owner_layer="visual_deck",
        related_block_ids=[],
        can_auto_repair=False,
    )


def _normalize_markdown_line(value: str) -> str:
    clean = str(value).strip()
    if not clean or re.fullmatch(r"[-|:\s]+", clean):
        return ""
    clean = re.sub(r"^#{1,6}\s*", "", clean)
    clean = re.sub(r"^(?:[-*+>]|\d+[.、])\s*", "", clean)
    clean = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = clean.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", "", clean)


def validate_source_metadata(step_results: list[dict], profiles: list[Any]) -> ValidationResult:
    tables: list[dict] = []
    for result in step_results:
        tables.extend(result.get("tables", []))
    tables_with_source = [t for t in tables if t.get("path") or t.get("source")]
    all_have_source = len(tables_with_source) == len(tables)
    return ValidationResult(
        gate_id="source_metadata",
        passed=all_have_source,
        severity="pass" if all_have_source else "fail",
        message=f"{len(tables_with_source)}/{len(tables)} tables have source metadata",
        details={"tables_with_source": len(tables_with_source), "total_tables": len(tables)},
    )


def validate_source_metadata_on_evidence(step_results: list[dict]) -> ValidationResult:
    tables: list[dict] = []
    charts: list[dict] = []
    for result in step_results:
        tables.extend(result.get("tables", []))
        charts.extend(result.get("charts", []))
    tables_no_source = [t.get("name") for t in tables if not (t.get("source") or t.get("path"))]
    charts_no_source = [c.get("name") for c in charts if not (c.get("source") or c.get("path"))]
    issues = len(tables_no_source) + len(charts_no_source)
    return ValidationResult(
        gate_id="source_metadata_on_evidence",
        passed=issues == 0,
        severity="pass" if issues == 0 else "fail",
        message=f"{issues} evidence item(s) missing source metadata",
        details={"tables_missing_source": tables_no_source, "charts_missing_source": charts_no_source},
    )


def validate_schema_compliance(blocks: list[dict]) -> ValidationResult:
    valid_types = {
        "heading",
        "prose",
        "table",
        "chart",
        "callout",
        "source_note",
        "markdown",
        "metric-strip",
        *VISUAL_BLOCK_TYPES,
    }
    invalid_blocks = [b for b in blocks if b.get("type") not in valid_types]
    return ValidationResult(
        gate_id="schema_compliance",
        passed=len(invalid_blocks) == 0,
        severity="pass" if not invalid_blocks else "fail",
        message=f"{len(invalid_blocks)} block(s) have invalid type",
        details={"invalid_blocks": len(invalid_blocks), "total_blocks": len(blocks)},
    )


def validate_layer_tags(blocks: list[dict]) -> ValidationResult:
    """Check renderer_target and block_origin use only allowed values."""
    invalid_targets: list[str] = []
    invalid_origins: list[str] = []
    for block in blocks:
        target = block.get("renderer_target")
        if target is not None and target not in RENDERER_TARGETS:
            invalid_targets.append(f"{block.get('id', '?')}: {target}")
        origin = block.get("block_origin")
        if origin is not None and origin not in BLOCK_ORIGINS:
            invalid_origins.append(f"{block.get('id', '?')}: {origin}")
    issues = len(invalid_targets) + len(invalid_origins)
    return ValidationResult(
        gate_id="layer_tags",
        passed=issues == 0,
        severity="pass" if not issues else "fail",
        message=f"{issues} block(s) have invalid renderer_target or block_origin",
        details={"invalid_targets": invalid_targets, "invalid_origins": invalid_origins},
        fix_hint=(
            None if issues == 0
            else f"Check {len(invalid_targets)} renderer_target(s) and "
                 f"{len(invalid_origins)} block_origin(s). Valid renderer_targets: "
                 f"{sorted(RENDERER_TARGETS)}. Valid origins: {sorted(BLOCK_ORIGINS)}. "
                 "Fix in build_visual_deck_blocks() or artifact_manifest.py."
        ),
        owner_layer="manifest",
        related_block_ids=[bid.split(":")[0] for bid in invalid_targets + invalid_origins],
        can_auto_repair=True,
    )


def validate_visual_report_richness(
    blocks: list[dict],
    delivery_mode: str | None = None,
) -> ValidationResult:
    visual_blocks = [b for b in blocks if b.get("type") in VISUAL_BLOCK_TYPES]
    chart_blocks = [b for b in blocks if b.get("type") == "chart"]
    metric_blocks = [b for b in blocks if b.get("type") == "metric-strip"]
    table_blocks = [b for b in blocks if b.get("type") == "table"]
    rich_count = len(visual_blocks) + len(chart_blocks) + len(metric_blocks)
    details = {
        "visual_blocks": len(visual_blocks),
        "chart_blocks": len(chart_blocks),
        "metric_blocks": len(metric_blocks),
        "table_blocks": len(table_blocks),
        "rich_count": rich_count,
        "delivery_mode": delivery_mode,
    }

    strict = _is_visual_report(delivery_mode)
    if rich_count == 0 and table_blocks:
        return ValidationResult(
            gate_id="visual_report_richness",
            passed=not strict,
            severity="warning",
            message=(
                "Visual report contains table evidence but no visual-first blocks"
                if not strict
                else "visual_report would benefit from chart, metric, or visual-first blocks beyond tables"
            ),
            details=details,
            fix_hint="Add chart_specs or visual_plan items to the Planner output. "
                     "Ensure build_visual_deck_blocks() produces at least 2 "
                     "non-table blocks (kpi_grid, trend_panel, etc.).",
            owner_layer="visual_deck",
        )

    if strict and table_blocks and rich_count < 2:
        return ValidationResult(
            gate_id="visual_report_richness",
            passed=False,
            severity="warning",
            message=(
                f"visual_report has only {rich_count} non-table visual component(s); "
                "core reports with table evidence need at least 2"
            ),
            details=details,
            fix_hint="Insufficient visual block count. Consider adding chart_specs "
                     "or visual_plan items that map to VISUAL_BLOCK_TYPES "
                     "(e.g., trend_panel, composition_panel, kpi_grid).",
            owner_layer="visual_deck",
        )

    if len(visual_blocks) < 2 and len(blocks) >= 6:
        return ValidationResult(
            gate_id="visual_report_richness",
            passed=True,
            severity="warning",
            message=(
                f"Only {len(visual_blocks)} visual-first block(s) found; "
                "management reports should usually include at least 2"
            ),
            details=details,
            fix_hint="Consider adding visual_plan items for key sections. "
                     "The visual deck compiler (visual_deck_blocks.py) can auto-generate "
                     "adaptive_story blocks for uncovered sections.",
            owner_layer="visual_deck",
        )

    return ValidationResult(
        gate_id="visual_report_richness",
        passed=True,
        severity="pass",
        message=(
            f"Visual richness OK: {len(visual_blocks)} visual block(s), "
            f"{len(chart_blocks)} chart block(s), {len(metric_blocks)} metric strip(s)"
        ),
        details=details,
    )


def validate_table_dominance(
    blocks: list[dict],
    delivery_mode: str | None = None,
) -> ValidationResult:
    total = len(blocks)
    table_count = sum(1 for b in blocks if b.get("type") == "table")
    if total == 0:
        return ValidationResult(
            gate_id="table_dominance",
            passed=True,
            severity="pass",
            message="No blocks to check",
            details={"table_count": 0, "total_blocks": 0, "delivery_mode": delivery_mode},
        )

    consecutive_tables = 0
    max_consecutive_tables = 0
    for block in blocks:
        if block.get("type") == "table":
            consecutive_tables += 1
            max_consecutive_tables = max(max_consecutive_tables, consecutive_tables)
        else:
            consecutive_tables = 0

    table_ratio = table_count / total
    evidence_blocks = [
        b for b in blocks
        if b.get("type") in {"table", "chart", "metric-strip", *VISUAL_BLOCK_TYPES}
    ]
    first_evidence_type = evidence_blocks[0].get("type") if evidence_blocks else None
    details = {
        "table_count": table_count,
        "total_blocks": total,
        "table_ratio": round(table_ratio, 4),
        "max_consecutive_tables": max_consecutive_tables,
        "first_evidence_block_type": first_evidence_type,
        "delivery_mode": delivery_mode,
    }

    strict = _is_visual_report(delivery_mode)
    if strict and first_evidence_type == "table":
        return ValidationResult(
            gate_id="table_dominance",
            passed=False,
            severity="fail",
            message="visual_report cannot use a table as the first evidence block",
            details=details,
            fix_hint="Place a chart or visual-first block (e.g., kpi_grid, trend_panel) "
                     "before the first table. compose_reading_flow() should interleave "
                     "visual blocks with evidence blocks.",
            owner_layer="reading_flow",
            can_auto_repair=True,
        )

    if strict and table_ratio > 0.5:
        return ValidationResult(
            gate_id="table_dominance",
            passed=False,
            severity="fail",
            message=f"visual_report is table-dominant ({table_count}/{total} blocks)",
            details=details,
            fix_hint=f"Table ratio is {table_ratio:.1%}. Reduce table count or add more "
                     "chart/metric/visual blocks. build_visual_deck_blocks() should "
                     "generate visual alternatives for table-heavy sections.",
            owner_layer="visual_deck",
            can_auto_repair=False,
        )

    if max_consecutive_tables >= 2 or table_ratio > 0.35:
        return ValidationResult(
            gate_id="table_dominance",
            passed=True,
            severity="warning",
            message=(
                f"Tables may dominate the report ({table_count}/{total} blocks; "
                f"max consecutive tables={max_consecutive_tables})"
            ),
            details=details,
            fix_hint="Interleave charts or visual blocks between consecutive tables. "
                     "compose_reading_flow() should avoid clustering tables.",
            owner_layer="reading_flow",
            can_auto_repair=True,
        )

    return ValidationResult(
        gate_id="table_dominance",
        passed=True,
        severity="pass",
        message=f"Table dominance OK ({table_count}/{total} blocks)",
        details=details,
    )


def validate_visual_evidence_links(
    blocks: list[dict],
    chart_ids: set[str] | None = None,
    table_ids: set[str] | None = None,
) -> ValidationResult:
    """Check evidence-backed visual blocks carry valid evidence ids.

    Missing evidence remains a warning so a sparse report can still render. Dangling
    evidence ids are a hard failure because they falsely imply source-backed claims.
    """
    visual_blocks = [b for b in blocks if b.get("type") in EVIDENCE_BACKED_VISUAL_TYPES]
    if not visual_blocks:
        return ValidationResult(
            gate_id="visual_evidence_links",
            passed=True,
            severity="pass",
            message="No evidence-backed visual blocks to check",
            details={"visual_blocks": 0},
        )
    valid_ids = (chart_ids or set()) | (table_ids or set())
    missing = [b.get("id") for b in visual_blocks if not b.get("evidence_ids")]
    dangling: list[str] = []
    for block in visual_blocks:
        for evidence_id in block.get("evidence_ids") or []:
            if valid_ids and evidence_id not in valid_ids:
                dangling.append(evidence_id)
    details = {
        "missing_block_ids": missing,
        "dangling_ids": dangling,
        "visual_blocks": len(visual_blocks),
        "valid_ids_count": len(valid_ids),
    }
    if dangling:
        return ValidationResult(
            gate_id="visual_evidence_links",
            passed=False,
            severity="fail",
            message=f"{len(dangling)} visual evidence id(s) reference non-existent charts/tables",
            details=details,
            fix_hint="Check attach_stable_source_ids() and evidence_ids produced by "
                     "build_visual_deck_blocks(); remove dangling ids instead of "
                     "falling back to unrelated evidence.",
            owner_layer="visual_deck",
            related_evidence_ids=dangling,
            can_auto_repair=True,
        )
    if missing:
        return ValidationResult(
            gate_id="visual_evidence_links",
            passed=True,
            severity="warning",
            message=f"{len(missing)} visual block(s) missing evidence ids; 0 dangling evidence id(s)",
            details=details,
            fix_hint=f"The {len(missing)} visual block(s) lack evidence_ids. "
                     "Check link_evidence() in evidence_linking.py — the tokenizer "
                     "may not match block text to available evidence. Consider "
                     "lowering the score threshold or adding more source tables/charts.",
            owner_layer="visual_deck",
            related_block_ids=missing,
        )
    return ValidationResult(
        gate_id="visual_evidence_links",
        passed=True,
        severity="pass",
        message=f"All {len(visual_blocks)} evidence-backed visual block(s) have evidence links",
        details={"visual_blocks": len(visual_blocks)},
    )


def validate_core_conclusion_visual_support(
    blocks: list[dict],
    chart_ids: set[str] | None = None,
    table_ids: set[str] | None = None,
    delivery_mode: str | None = None,
) -> ValidationResult:
    """Require visual_report core conclusions to be supported by chart or visual evidence."""
    if not _is_visual_report(delivery_mode):
        return ValidationResult(
            gate_id="core_conclusion_visual_support",
            passed=True,
            severity="pass",
            message="Core conclusion visual support is enforced only for visual_report delivery",
            details={"delivery_mode": delivery_mode},
        )

    chart_ids = chart_ids or set()
    table_ids = table_ids or set()
    narrative_blocks = [b for b in blocks if b.get("type") in {"markdown", "prose"}]
    core_blocks = [
        b for b in narrative_blocks
        if b.get("evidence_priority") == "primary"
        or b.get("claim_ids")
        or any(token.lower() in _block_text(b).lower() for token in CORE_CONCLUSION_TOKENS)
    ]
    if not core_blocks:
        core_blocks = [b for b in narrative_blocks if b.get("evidence_ids")][:2]

    visual_evidence_ids: set[str] = set(chart_ids)
    for block in blocks:
        if block.get("type") in NON_TABLE_VISUAL_TYPES:
            if block.get("chart_id"):
                visual_evidence_ids.add(block["chart_id"])
            visual_evidence_ids.update(block.get("evidence_ids") or [])

    supported_core_blocks: list[str] = []
    chart_supported_core_blocks: list[str] = []
    for block in core_blocks:
        evidence_ids = set(block.get("evidence_ids") or [])
        if evidence_ids & visual_evidence_ids:
            supported_core_blocks.append(str(block.get("id") or block.get("title") or "core_block"))
        if evidence_ids & chart_ids:
            chart_supported_core_blocks.append(str(block.get("id") or block.get("title") or "core_block"))

    details = {
        "core_blocks": len(core_blocks),
        "supported_core_blocks": len(supported_core_blocks),
        "chart_supported_core_blocks": len(chart_supported_core_blocks),
        "chart_ids": sorted(chart_ids),
        "table_ids_count": len(table_ids),
        "visual_evidence_ids_count": len(visual_evidence_ids),
    }

    if not core_blocks:
        return ValidationResult(
            gate_id="core_conclusion_visual_support",
            passed=True,
            severity="warning",
            message="No core conclusion block found to validate against visual evidence",
            details=details,
        )

    if not supported_core_blocks:
        return ValidationResult(
            gate_id="core_conclusion_visual_support",
            passed=False,
            severity="fail",
            message="visual_report core conclusions are not backed by chart or visual-first evidence",
            details=details,
            fix_hint="Ensure core conclusion blocks (containing 核心结论/执行摘要 tokens) "
                     "have evidence_ids linking to chart or visual block ids. "
                     "Check link_evidence() score thresholds and evidence tokenizer matching.",
            owner_layer="visual_deck",
            related_block_ids=[str(b.get("id") or b.get("title") or "core_block") for b in core_blocks],
            can_auto_repair=False,
        )

    if chart_ids and not chart_supported_core_blocks:
        return ValidationResult(
            gate_id="core_conclusion_visual_support",
            passed=True,
            severity="warning",
            message="Core conclusions are visually supported, but none directly reference chart evidence",
            details=details,
            fix_hint="Core conclusions are backed by visual blocks but none by charts. "
                     "Consider linking a chart to the core conclusion block via evidence_ids.",
            owner_layer="visual_deck",
            related_block_ids=supported_core_blocks,
        )

    return ValidationResult(
        gate_id="core_conclusion_visual_support",
        passed=True,
        severity="pass",
        message="Core conclusions are backed by visual evidence",
        details=details,
    )


def validate_chart_contracts(step_results: list[dict]) -> ValidationResult:
    charts: list[dict] = []
    for result in step_results:
        charts.extend(result.get("charts", []))
    from app.tools.chart_contract import FILE_CHART_TYPES, SUPPORTED_CHART_TYPES
    valid_chart_types = SUPPORTED_CHART_TYPES | FILE_CHART_TYPES
    invalid_charts = [c for c in charts if c.get("type") not in valid_chart_types]
    return ValidationResult(
        gate_id="chart_contracts",
        passed=len(invalid_charts) == 0,
        severity="pass" if not invalid_charts else "fail",
        message=f"{len(invalid_charts)} chart(s) have unsupported type",
        details={"invalid_charts": len(invalid_charts), "total_charts": len(charts)},
    )


def _normalize_raw_chart_type(raw: str) -> str:
    return {
        "png": "bar",
        "jpg": "bar",
        "jpeg": "bar",
        "svg": "bar",
        "html": "bar",
        "plotly": "bar",
    }.get(raw, raw)


def validate_chart_contract_compatibility(step_results: list[dict]) -> ValidationResult:
    try:
        from app.tools.chart_contract import SUPPORTED_CHART_TYPES
    except ImportError:
        return ValidationResult(
            gate_id="chart_contract_compat",
            passed=True,
            severity="warning",
            message="chart_contract.py not available",
        )
    charts: list[dict] = []
    for result in step_results:
        charts.extend(result.get("charts", []))
    invalid = []
    for chart in charts:
        chart_type = chart.get("type", "bar")
        normalized = _normalize_raw_chart_type(chart_type)
        if normalized not in SUPPORTED_CHART_TYPES and chart_type not in SUPPORTED_CHART_TYPES:
            invalid.append(f"{chart.get('name', 'Unknown')}: type '{chart_type}' not canonical")
    return ValidationResult(
        gate_id="chart_contract_compat",
        passed=len(invalid) == 0,
        severity="pass" if not invalid else "fail",
        message=f"{len(invalid)} chart(s) have non-canonical types" if invalid else "All charts use canonical types",
        details={"invalid": invalid, "total": len(charts)},
    )


def validate_context_caveats(plan_caveats: list[str], profiles: list[Any]) -> ValidationResult:
    caveat_count = len(plan_caveats)
    return ValidationResult(
        gate_id="context_caveats",
        passed=True,
        severity="warning" if caveat_count == 0 else "pass",
        message=f"Found {caveat_count} caveat(s) in plan",
        details={"caveat_count": caveat_count},
    )


def validate_project_context_coverage(
    project_contexts: list | None,
    semantic_layer_data: dict | None,
) -> ValidationResult:
    context_count = len(project_contexts) if project_contexts else 0
    sl_metrics = len(semantic_layer_data.get("metrics", [])) if semantic_layer_data else 0
    warnings = []
    if context_count == 0:
        warnings.append("No project context items defined")
    if sl_metrics == 0:
        warnings.append("No semantic-layer metrics defined")
    return ValidationResult(
        gate_id="project_context_coverage",
        passed=True,
        severity="warning" if warnings else "pass",
        message="; ".join(warnings) if warnings else "Project context and semantic layer are populated",
        details={"context_count": context_count, "sl_metrics": sl_metrics},
    )


def validate_renderability(artifacts: list[dict]) -> ValidationResult:
    renderable_types = {
        "structured_report",
        "markdown_report",
        "html_report",
        "table",
        "chart",
        "dashboard",
        "run_log",
        "visual_report",
        "notebook",
    }
    non_renderable = [a for a in artifacts if a.get("type") not in renderable_types]
    return ValidationResult(
        gate_id="renderability",
        passed=len(non_renderable) == 0,
        severity="pass" if not non_renderable else "fail",
        message=f"{len(non_renderable)} artifact(s) may not render",
        details={"non_renderable": len(non_renderable), "total_artifacts": len(artifacts)},
    )


def validate_chart_encoding(step_results: list[dict]) -> ValidationResult:
    charts: list[dict] = []
    for result in step_results:
        charts.extend(result.get("charts", []))
    issues = []
    for chart in charts:
        chart_type = chart.get("type")
        if chart_type in ("bar", "line", "area"):
            if not chart.get("x") and not chart.get("x_axis"):
                issues.append(f"Chart '{chart.get('name')}' missing x-axis binding")
            if not chart.get("y") and not chart.get("y_axis"):
                issues.append(f"Chart '{chart.get('name')}' missing y-axis binding")
    return ValidationResult(
        gate_id="chart_encoding",
        passed=len(issues) == 0,
        severity="pass" if not issues else "fail",
        message=f"{len(issues)} chart encoding issue(s)",
        details={"issues": issues} if issues else None,
        fix_hint=(
            None if not issues
            else f"Missing axis bindings in {len(issues)} chart(s). "
                 "Ensure generated code provides x/y fields or x_axis/y_axis "
                 "for bar, line, and area charts. See chart_contract.py for "
                 "required encoding fields."
        ),
        owner_layer="execution",
        can_auto_repair=False,
    )


def validate_report_quality(blocks: list[dict]) -> ValidationResult:
    """Validate structured report planning metadata and claim/action traceability."""
    issues: list[str] = []
    warnings: list[str] = []
    claim_blocks = [b for b in blocks if b.get("claim_ids")]
    action_blocks = [b for b in blocks if b.get("type") == "next_action_list" or b.get("action_ids")]
    primary_blocks = [b for b in blocks if b.get("evidence_priority") == "primary"]
    appendix_claim_blocks = [b for b in claim_blocks if b.get("evidence_priority") == "appendix"]
    missing_section_role = [b.get("id") for b in claim_blocks + action_blocks if not b.get("section_role")]

    for block in claim_blocks:
        if not block.get("evidence_ids"):
            issues.append(f"Claim block {block.get('id')} lacks evidence_ids")
    for block in action_blocks:
        if not block.get("action_ids") and block.get("type") == "next_action_list":
            origin = block.get("block_origin")
            items = block.get("items") or []
            if origin == "visual_deck" and items:
                warnings.append(
                    f"Visual deck next_action_list {block.get('id')} has items but no action_ids"
                )
            else:
                issues.append(f"Action block {block.get('id')} lacks action_ids")
        if not block.get("evidence_ids"):
            warnings.append(f"Action block {block.get('id')} has no supporting evidence_ids")
    if appendix_claim_blocks and not primary_blocks:
        issues.append(f"{len(appendix_claim_blocks)} appendix block(s) are attached to core claims")
    if claim_blocks and not primary_blocks:
        warnings.append("Claims exist but no block is marked primary")
    if missing_section_role:
        warnings.append(f"{len(missing_section_role)} claim/action block(s) missing section_role")

    details = {
        "claim_blocks": len(claim_blocks),
        "action_blocks": len(action_blocks),
        "primary_blocks": len(primary_blocks),
        "appendix_claim_blocks": len(appendix_claim_blocks),
        "missing_section_role": missing_section_role,
        "issues": issues,
        "warnings": warnings,
    }
    if issues:
        return ValidationResult(
            gate_id="report_quality",
            passed=False,
            severity="fail",
            message=f"{len(issues)} report quality issue(s)",
            details=details,
        )
    if warnings:
        return ValidationResult(
            gate_id="report_quality",
            passed=True,
            severity="warning",
            message=f"{len(warnings)} report quality warning(s)",
            details=details,
        )
    return ValidationResult(
        gate_id="report_quality",
        passed=True,
        severity="pass",
        message="Report quality metadata is traceable",
        details=details,
    )


def _artifact_scan_text(artifact: dict) -> str:
    parts = [artifact.get("title"), artifact.get("content"), artifact.get("data")]
    return "\n".join(str(part) for part in parts if part is not None)[:200_000]


def _validation_scan_artifacts(report_md: str, blocks: list[dict], artifacts: list[dict]) -> list[dict]:
    return [
        *artifacts,
        {"type": "markdown_report", "title": "Synthesis Markdown", "content": report_md},
        {"type": "structured_report", "title": "Structured Blocks", "data": {"blocks": blocks}},
    ]


def validate_source_safety(artifacts: list[dict]) -> ValidationResult:
    sensitive_patterns = [
        "".join(("pass", "word")),
        "".join(("sec", "ret")),
        "".join(("tok", "en")),
        "api" + "_key",
        "api" + "key",
        "creden" + "tial",
        "au" + "th",
        "private" + "_key",
        "access" + "_key",
    ]
    issues = []
    for artifact in artifacts:
        content = _artifact_scan_text(artifact).lower()
        for pattern in sensitive_patterns:
            if pattern in content:
                issues.append(f"Artifact '{artifact.get('title')}' may contain unsafe source text: {pattern}")
    return ValidationResult(
        gate_id="source_safety",
        passed=len(issues) == 0,
        severity="pass" if not issues else "fail",
        message=f"{len(issues)} source safety issue(s)",
        details={"issues": issues} if issues else None,
    )


def _has_product_code_context(text: str, match_start: int, match_end: int) -> bool:
    window = text[max(0, match_start - 60):match_end + 60]
    return any(field in window for field in _PRODUCT_CODE_FIELDS)


def _has_phone_context(text: str, match_start: int, match_end: int) -> bool:
    window = text[max(0, match_start - 40):match_end + 40]
    return any(kw in window.lower() for kw in _PHONE_CONTEXT_KEYWORDS)


def validate_sensitive_payload(artifacts: list[dict]) -> ValidationResult:
    issues: list[str] = []
    for artifact in artifacts:
        content = _artifact_scan_text(artifact)
        email_matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", content)
        if email_matches:
            issues.append(f"Artifact '{artifact.get('title')}' may contain PII: {len(email_matches)} email match(es)")

        for match in _PHONE_FORMATTED_RE.finditer(content):
            if not _has_product_code_context(content, match.start(), match.end()):
                issues.append(
                    f"Artifact '{artifact.get('title')}' may contain phone number: {match.group()}"
                )

        for match in _PHONE_PLAIN_RE.finditer(content):
            if _has_phone_context(content, match.start(), match.end()) and not _has_product_code_context(content, match.start(), match.end()):
                issues.append(
                    f"Artifact '{artifact.get('title')}' may contain phone number: {match.group()}"
                )

        card_matches = [
            match.group(0)
            for match in _CARD_CANDIDATE_RE.finditer(content)
            if _passes_luhn(match.group(0))
        ]
        if card_matches:
            issues.append(
                f"Artifact '{artifact.get('title')}' may contain card number(s): "
                f"{len(card_matches)} match(es)"
            )
    return ValidationResult(
        gate_id="sensitive_payload",
        passed=len(issues) == 0,
        severity="pass" if not issues else "warning",
        message=f"{len(issues)} potential sensitive payload issue(s)",
        details={"issues": issues} if issues else None,
    )


def validate_file_chart_asset_refs(
    artifacts: list[Any],
    artifacts_dir: str | None = None,
) -> ValidationResult:
    """Verify file-chart artifact refs are well-formed and the files exist."""
    from pathlib import Path

    bad_refs: list[str] = []
    missing_files: list[str] = []

    for art in artifacts:
        data = getattr(art, "data", None) or {}
        if isinstance(data, dict) and data.get("render_mode") == "file":
            path_val = data.get("path") or data.get("asset_name") or ""
            if not path_val or path_val == "<local_path>":
                bad_refs.append(f"{data.get('chart_type', 'unknown')}: missing or redacted path")
                continue
            if "/Users/" in path_val or "/home/" in path_val or "localhost" in path_val:
                bad_refs.append(f"{data.get('chart_type', 'unknown')}: path contains leaked local ref: {path_val}")
                continue
            name = Path(str(path_val)).name
            if not name or Path(name).suffix.lower() not in {".html", ".png", ".jpg", ".jpeg", ".svg"}:
                bad_refs.append(f"{data.get('chart_type', 'unknown')}: unrecognized extension: {path_val}")
                continue
            if artifacts_dir:
                file_path = Path(artifacts_dir) / name
                if not file_path.is_file():
                    missing_files.append(name)

    issues = bad_refs + [f"missing chart file: {f}" for f in missing_files]
    return ValidationResult(
        gate_id="file_chart_asset_refs",
        passed=len(issues) == 0,
        severity="pass" if not issues else "warning",
        message=f"{len(issues)} file chart asset reference issue(s)" if issues else "All file chart asset refs valid",
        details={"issues": issues} if issues else None,
    )


def validate_web_report_chart_embeds(
    run_artifacts: list[Any],
    web_report_path: str | None = None,
) -> ValidationResult:
    """Verify charts are actually embedded in the Web Report HTML."""
    import re
    from pathlib import Path

    file_chart_count = 0
    for art in run_artifacts:
        data = getattr(art, "data", None) or {}
        if isinstance(data, dict) and data.get("render_mode") == "file":
            file_chart_count += 1

    if file_chart_count == 0:
        return ValidationResult(
            gate_id="web_report_chart_embeds",
            passed=True,
            severity="pass",
            message="No file charts to embed",
        )

    if not web_report_path or not Path(web_report_path).is_file():
        return ValidationResult(
            gate_id="web_report_chart_embeds",
            passed=False,
            severity="warning",
            message=f"Web Report HTML not found at {web_report_path}",
        )

    html = Path(web_report_path).read_text(encoding="utf-8", errors="replace")
    iframe_count = len(re.findall(r"<iframe\s", html))
    plain_refs = re.findall(r"\[[A-Za-z0-9_.-]+\.html\](?!\()", html)

    issues: list[str] = []
    if iframe_count == 0:
        issues.append(f"{file_chart_count} file chart(s) generated but 0 iframe(s) in web_report.html")
    elif iframe_count < file_chart_count:
        issues.append(f"only {iframe_count}/{file_chart_count} chart(s) embedded in web_report.html")
    if plain_refs:
        issues.append(f"{len(plain_refs)} plain chart ref(s) still present (should be iframes): {', '.join(plain_refs[:5])}")

    return ValidationResult(
        gate_id="web_report_chart_embeds",
        passed=len(issues) == 0,
        severity="pass" if not issues else "warning",
        message=f"{len(issues)} web report chart embed issue(s)" if issues else f"All {file_chart_count} chart(s) embedded",
        details={"file_chart_count": file_chart_count, "iframe_count": iframe_count, "issues": issues} if issues else None,
    )


def validate_report_evidence_integration_postrun(
    report_md: str,
    step_results: list[dict],
    chart_specs: list[dict] | None = None,
    blocks: list[dict] | None = None,
    manifest_tables: list[dict] | None = None,
    manifest_charts: list[dict] | None = None,
) -> ValidationResult:
    """Post-run audit: were primary/supporting tables/charts integrated into report_md?"""
    from app.tools.report_evidence import missing_report_evidence_integrations

    missing = missing_report_evidence_integrations(
        report_md=report_md,
        execution_results=step_results,
        chart_specs=chart_specs,
        blocks=blocks,
        manifest_tables=manifest_tables,
        manifest_charts=manifest_charts,
    )
    if not missing:
        return ValidationResult(
            gate_id="report_evidence_integration",
            passed=True,
            severity="pass",
            message="All required primary/supporting evidence integrated or structurally bound",
        )
    return ValidationResult(
        gate_id="report_evidence_integration",
        passed=False,
        severity="warning",
        message=f"{len(missing)} evidence artifact(s) not integrated into report_md",
        details={"missing": missing},
    )


def validate_completion_mode(delivery_mode: str | None) -> ValidationResult:
    valid_modes = {
        "structured_report",
        "markdown",
        "html",
        "pdf",
        "google_docs",
        "google_slides",
        "visual_report",
        "plan_only",
    }
    is_valid = delivery_mode is None or delivery_mode in valid_modes
    return ValidationResult(
        gate_id="completion_mode",
        passed=is_valid,
        severity="pass" if is_valid else "fail",
        message=f"Delivery mode '{delivery_mode}' is {'valid' if is_valid else 'invalid'}",
        details={"delivery_mode": delivery_mode, "valid_modes": list(valid_modes)},
    )


def validate_preflight(context_gaps: list[str], preflight_built: bool = True) -> ValidationResult:
    if not preflight_built:
        return ValidationResult(
            gate_id="preflight",
            passed=False,
            severity="fail",
            message="Preflight envelope was not built",
            details={"preflight_built": False},
        )
    critical_gaps = [g for g in context_gaps if "No datasets selected" in g]
    warning_gaps = [g for g in context_gaps if g not in critical_gaps]
    if critical_gaps:
        return ValidationResult(
            gate_id="preflight",
            passed=False,
            severity="fail",
            message=f"Preflight found {len(critical_gaps)} critical gap(s): {', '.join(critical_gaps)}",
            details={
                "critical_gaps": critical_gaps,
                "warning_gaps": warning_gaps,
                "total_gaps": len(context_gaps),
            },
        )
    if warning_gaps:
        return ValidationResult(
            gate_id="preflight",
            passed=True,
            severity="warning",
            message=f"Preflight passed with {len(warning_gaps)} warning(s): {', '.join(warning_gaps)}",
            details={"warning_gaps": warning_gaps, "total_gaps": len(context_gaps)},
        )
    return ValidationResult(
        gate_id="preflight",
        passed=True,
        severity="pass",
        message="Preflight complete, no gaps detected",
        details={"total_gaps": 0},
    )


def validate_evidence_references(
    blocks: list[dict],
    chart_ids: set[str] | None = None,
    table_ids: set[str] | None = None,
) -> ValidationResult:
    markdown_blocks = [b for b in blocks if b.get("type") in ("markdown", "prose")]
    if not markdown_blocks:
        return ValidationResult(
            gate_id="evidence_references",
            passed=True,
            severity="pass",
            message="No markdown/prose blocks to check",
            details={"blocks_with_evidence": 0, "total_markdown": 0},
        )
    valid_ids = (chart_ids or set()) | (table_ids or set())
    blocks_with_evidence = [b for b in markdown_blocks if b.get("evidence_ids")]
    count_with = len(blocks_with_evidence)
    total = len(markdown_blocks)
    dangling_ids: list[str] = []
    for block in blocks_with_evidence:
        for evidence_id in block["evidence_ids"]:
            if valid_ids and evidence_id not in valid_ids:
                dangling_ids.append(evidence_id)
    if count_with == 0:
        return ValidationResult(
            gate_id="evidence_references",
            passed=False,
            severity="fail",
            message=f"0/{total} markdown blocks have evidence references",
            details={"blocks_with_evidence": 0, "total_markdown": total},
            fix_hint="No markdown blocks have evidence_ids. Check link_evidence() in "
                     "evidence_linking.py and artifact_manifest.py build loop. "
                     "The tokenizer may be failing to match block text against "
                     "available chart/table names.",
            owner_layer="manifest",
            can_auto_repair=False,
        )
    if dangling_ids:
        return ValidationResult(
            gate_id="evidence_references",
            passed=False,
            severity="fail",
            message=(
                f"{count_with}/{total} blocks have evidence, but {len(dangling_ids)} id(s) "
                f"reference non-existent charts/tables: {dangling_ids[:5]}"
            ),
            details={
                "blocks_with_evidence": count_with,
                "total_markdown": total,
                "dangling_ids": dangling_ids,
                "valid_ids_count": len(valid_ids),
            },
            fix_hint=f"Remove {len(dangling_ids)} dangling evidence id(s) from markdown "
                     "blocks. These ids do not exist in manifest.charts or manifest.tables. "
                     "Check attach_stable_source_ids() in visual_deck_evidence.py.",
            owner_layer="manifest",
            related_evidence_ids=dangling_ids,
            can_auto_repair=True,
        )
    if count_with < total:
        return ValidationResult(
            gate_id="evidence_references",
            passed=True,
            severity="warning",
            message=f"{count_with}/{total} markdown blocks have evidence references",
            details={"blocks_with_evidence": count_with, "total_markdown": total},
            fix_hint=f"{total - count_with} markdown blocks lack evidence_ids. "
                     "Consider linking remaining blocks to available evidence items.",
            owner_layer="manifest",
        )
    return ValidationResult(
        gate_id="evidence_references",
        passed=True,
        severity="pass",
        message=f"All {total} markdown blocks have evidence references",
        details={"blocks_with_evidence": total, "total_markdown": total},
    )


def run_validation_gates(
    step_results: list[dict],
    report_md: str,
    blocks: list[dict],
    plan_caveats: list[str],
    profiles: list[Any],
    artifacts: list[dict],
    delivery_mode: str | None = None,
    context_gaps: list[str] | None = None,
    preflight_built: bool = True,
    project_contexts: list | None = None,
    semantic_layer_data: dict | None = None,
    manifest_chart_ids: set[str] | None = None,
    manifest_table_ids: set[str] | None = None,
    chart_specs: list | None = None,
) -> list[ValidationResult]:
    safety_artifacts = _validation_scan_artifacts(report_md, blocks, artifacts)
    has_chart_evidence = any(result.get("charts") for result in step_results)
    has_table_evidence = any(result.get("tables") for result in step_results)
    return [
        validate_markdown_content_sanity(
            report_md=report_md,
            chart_specs=chart_specs,
            has_chart_evidence=has_chart_evidence,
            has_table_evidence=has_table_evidence,
        ),
        validate_preflight(context_gaps or [], preflight_built),
        validate_evidence_coverage(step_results, report_md),
        validate_markdown_content_preservation(report_md, blocks),
        validate_visual_section_coverage(report_md, blocks),
        validate_evidence_references(blocks, manifest_chart_ids, manifest_table_ids),
        validate_report_quality(blocks),
        validate_source_metadata(step_results, profiles),
        validate_source_metadata_on_evidence(step_results),
        validate_schema_compliance(blocks),
        validate_layer_tags(blocks),
        validate_visual_report_richness(blocks, delivery_mode),
        validate_table_dominance(blocks, delivery_mode),
        validate_visual_evidence_links(blocks, manifest_chart_ids, manifest_table_ids),
        validate_core_conclusion_visual_support(blocks, manifest_chart_ids, manifest_table_ids, delivery_mode),
        validate_chart_contracts(step_results),
        validate_chart_contract_compatibility(step_results),
        validate_context_caveats(plan_caveats, profiles),
        validate_project_context_coverage(project_contexts, semantic_layer_data),
        validate_semantic_ambiguity(semantic_layer_data),
        validate_renderability(artifacts),
        validate_chart_encoding(step_results),
        validate_source_safety(safety_artifacts),
        validate_sensitive_payload(safety_artifacts),
        validate_completion_mode(delivery_mode),
    ]


def get_validation_tool_definitions() -> list[dict]:
    descriptions = {
        "validate_evidence_coverage": "Check if every key claim maps to table/chart evidence",
        "validate_markdown_content_preservation": "Require every substantive Markdown line to remain in the designed report flow",
        "validate_visual_section_coverage": "Audit high-signal prose sections and propose safe adaptive layouts for gaps",
        "validate_evidence_references": "Check markdown/prose evidence_ids against supporting data",
        "validate_report_quality": "Check claim/action traceability and report-plan metadata",
        "validate_visual_report_richness": "Fail visual_report delivery when the main report lacks non-table visual support",
        "validate_table_dominance": "Warn or fail when tables dominate the report reading flow",
        "validate_visual_evidence_links": "Check evidence-backed visual blocks carry valid ids",
        "validate_core_conclusion_visual_support": "Require visual_report core conclusions to cite chart or visual-first evidence",
        "validate_source_metadata_on_evidence": "Check evidence items carry source or path metadata",
        "validate_source_metadata": "Verify tables carry source metadata",
        "validate_schema_compliance": "Confirm report blocks satisfy the schema contract",
        "validate_layer_tags": "Verify renderer_target and block_origin use allowed values",
        "validate_chart_contracts": "Check chart types follow the chart-rules contract",
        "validate_chart_contract_compatibility": "Check chart types against canonical contracts",
        "validate_context_caveats": "Confirm missing context and data quality issues are surfaced",
        "validate_project_context_coverage": "Warn about missing project context or semantic layer",
        "validate_semantic_ambiguity": "Detect ambiguous or conflicting metric definitions",
        "validate_renderability": "Verify generated artifacts can render or have fallback",
        "validate_chart_encoding": "Check chart axis bindings and encoding correctness",
        "validate_source_safety": "Scan artifacts for unsafe source text",
        "validate_sensitive_payload": "Scan artifacts for PII patterns",
        "validate_file_chart_asset_refs": "Verify file-chart artifact paths are valid and files exist",
        "validate_web_report_chart_embeds": "Verify charts are actually embedded as iframes in web_report.html",
        "validate_report_evidence_integration_postrun": "Check all generated tables/charts are integrated into report_md",
        "validate_completion_mode": "Confirm report delivery mode is valid",
        "validate_preflight": "Verify preflight envelope was built and check gaps",
    }
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        for name, description in descriptions.items()
    ]
