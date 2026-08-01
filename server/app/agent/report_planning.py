"""Deterministic report-planning helpers.

This module extracts lightweight, evidence-aware metadata from the report text and
manifest blocks. It does not invent analysis; it only classifies and structures
what the run already produced so renderers and validators can reason about the
report as decision material instead of opaque Markdown.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.models.schemas import (
    ActionItem,
    ArtifactBlock,
    ArtifactBlockType,
    ManifestSource,
    ReportClaim,
    ReportIntent,
    ReportPlan,
    ReportSection,
)


EXECUTIVE_TOKENS = (
    "executive", "management", "board", "管理层", "经营", "概览", "月报", "复盘", "业绩", "业务",
)
OPS_TOKENS = ("ops", "operation", "运营", "异常", "告警", "处理", "动作", "优先级")
FINANCE_TOKENS = ("finance", "financial", "revenue", "cost", "margin", "预算", "收入", "成本", "利润", "毛利")
PRODUCT_TOKENS = ("product", "retention", "conversion", "activation", "产品", "留存", "转化", "漏斗")
DASHBOARD_TOKENS = ("dashboard", "看板", "visual", "可视化", "速览", "kpi", "指标")
DETAILED_TOKENS = ("deep dive", "详细", "诊断", "根因", "拆解", "原因", "分析")
ACTION_TOKENS = ("建议", "行动", "下一步", "todo", "action", "recommend", "priority", "owner")
PRIMARY_SECTION_TOKENS = (
    "执行摘要", "核心结论", "结论", "summary", "executive summary", "recommendation", "建议", "风险", "risk",
)
APPENDIX_TOKENS = ("附录", "appendix", "补充", "debug", "日志", "清单", "index")
RISK_TOKENS = ("风险", "risk", "异常", "缺口", "告警", "下降", "拖累", "问题")
RECOMMENDATION_TOKENS = ("建议", "行动", "下一步", "recommend", "action", "should", "需要", "优先")
DIAGNOSIS_TOKENS = ("原因", "根因", "诊断", "驱动", "贡献", "影响", "because", "driver")
FORECAST_TOKENS = ("预测", "forecast", "预计", "未来", "scenario", "情景")
HIGH_IMPACT_TOKENS = ("显著", "关键", "核心", "高优先级", "critical", "major", "重点")
LOW_IMPACT_TOKENS = ("轻微", "低优先级", "optional", "low")
SHORT_TERM_TOKENS = ("本周", "短期", "立即", "now", "urgent")
LONG_TERM_TOKENS = ("长期", "未来", "季度", "year", "长期")


SECTION_TEMPLATES: dict[str, list[tuple[str, str, list[str]]]] = {
    "executive": [
        ("summary", "执行摘要", ["page_summary", "kpi_grid"]),
        ("key_findings", "关键变化", ["trend_panel", "leaderboard_pair", "composition_panel"]),
        ("risks", "风险与关注点", ["risk_panel"]),
        ("actions", "建议行动", ["next_action_list"]),
        ("appendix", "附录证据", ["table", "chart"]),
    ],
    "analyst": [
        ("scope", "问题与口径", ["markdown"]),
        ("method", "方法与数据", ["data_quality_panel", "table"]),
        ("findings", "分析发现", ["chart", "table"]),
        ("caveats", "局限性", ["risk_panel"]),
        ("appendix", "附录证据", ["table", "chart"]),
    ],
    "ops": [
        ("anomalies", "异常与影响", ["risk_panel", "leaderboard_pair"]),
        ("scope", "影响范围", ["composition_panel", "table"]),
        ("actions", "处理建议", ["next_action_list"]),
        ("appendix", "附录证据", ["table", "chart"]),
    ],
    "finance": [
        ("summary", "财务摘要", ["kpi_grid"]),
        ("variance", "差异与贡献", ["delta_bridge", "leaderboard_pair"]),
        ("risks", "风险与预测", ["risk_panel", "forecast_band"]),
        ("actions", "建议行动", ["next_action_list"]),
        ("appendix", "附录证据", ["table", "chart"]),
    ],
    "product": [
        ("summary", "产品表现摘要", ["kpi_grid"]),
        ("funnel", "转化与留存", ["trend_panel", "leaderboard_pair"]),
        ("diagnosis", "机会与原因", ["decision_matrix", "composition_panel"]),
        ("actions", "建议行动", ["next_action_list"]),
        ("appendix", "附录证据", ["table", "chart"]),
    ],
}

EVIDENCE_BUDGETS = {
    "executive": {"primary_blocks": 8, "appendix_tables": 3, "raw_tables": 0},
    "analyst": {"primary_blocks": 12, "appendix_tables": 8, "raw_tables": 2},
    "ops": {"primary_blocks": 10, "appendix_tables": 4, "raw_tables": 0},
    "finance": {"primary_blocks": 10, "appendix_tables": 5, "raw_tables": 1},
    "product": {"primary_blocks": 10, "appendix_tables": 4, "raw_tables": 0},
}


def infer_report_intent(title: str, report_md: str) -> ReportIntent:
    """Infer audience/layout intent from stable report cues.

    The planner remains deterministic by using explicit text signals rather than
    asking the LLM to restate intent after the analysis has already run.
    """
    text = f"{title}\n{report_md}".lower()
    rationale: list[str] = []

    audience = "analyst"
    if _contains_any(text, EXECUTIVE_TOKENS):
        audience = "executive"
        rationale.append("executive_or_business_language")
    elif _contains_any(text, FINANCE_TOKENS):
        audience = "finance"
        rationale.append("finance_language")
    elif _contains_any(text, OPS_TOKENS):
        audience = "ops"
        rationale.append("operations_language")
    elif _contains_any(text, PRODUCT_TOKENS):
        audience = "product"
        rationale.append("product_language")

    report_format = "dashboard" if _contains_any(text, DASHBOARD_TOKENS) else "deep_dive"
    if report_format == "dashboard":
        rationale.append("dashboard_language")

    depth = "detailed" if _contains_any(text, DETAILED_TOKENS) else "standard"
    if depth == "detailed":
        rationale.append("diagnostic_language")

    visual_density = "high" if audience in {"executive", "ops"} or report_format == "dashboard" else "medium"
    if len(report_md) < 1200 and audience == "analyst":
        visual_density = "low"

    confidence = "high" if rationale else "medium"
    return ReportIntent(
        audience=audience,
        format=report_format,
        depth=depth,
        visual_density=visual_density,
        confidence=confidence,
        rationale=rationale,
    )


def evidence_priority_for_text(text: str, *, has_evidence: bool = True) -> str:
    """Classify how prominently a report block should appear."""
    lower = text.lower()
    if _contains_any(lower, APPENDIX_TOKENS):
        return "appendix"
    if has_evidence and _contains_any(lower, PRIMARY_SECTION_TOKENS):
        return "primary"
    if has_evidence:
        return "secondary"
    return "diagnostic"


def attach_claims_to_blocks(
    blocks: list[ArtifactBlock],
    sources: list[ManifestSource],
    plan_caveats: list[str] | None = None,
    *,
    max_claims: int = 8,
) -> list[ReportClaim]:
    """Extract evidence-aware claims and attach claim ids back to blocks.

    Claims are intentionally conservative: only markdown blocks with evidence ids
    become claims. This avoids turning unsupported prose into authoritative
    conclusions.
    """
    claims: list[ReportClaim] = []
    source_ids = [source.id for source in sources[:3]]
    caveats = plan_caveats or []

    for block in blocks:
        if len(claims) >= max_claims:
            break
        if block.type != ArtifactBlockType.markdown or not block.evidence_ids:
            continue
        text = _first_useful_statement(block.body or "")
        if not text:
            continue

        confidence = "high" if block.evidence_ids and not caveats else "medium"
        claim = ReportClaim(
            text=text,
            evidence_ids=list(dict.fromkeys(block.evidence_ids)),
            source_ids=source_ids,
            confidence=confidence,
            caveats=caveats[:3],
            claim_type=classify_claim_type(text),
            impact=classify_claim_impact(text),
            time_horizon=classify_time_horizon(text),
            metric_refs=extract_metric_refs(text),
        )
        claims.append(claim)
        block.claim_ids.append(claim.id)
        if block.evidence_priority == "secondary":
            block.evidence_priority = evidence_priority_for_text(block.body or "", has_evidence=True)

    primary_evidence = {eid for claim in claims if claim.confidence in {"high", "medium"} for eid in claim.evidence_ids}
    for block in blocks:
        if block.evidence_ids and any(eid in primary_evidence for eid in block.evidence_ids):
            if block.evidence_priority not in {"appendix", "hidden"}:
                block.evidence_priority = "primary"

    return claims


def action_items_from_markdown(report_md: str, *, max_items: int = 6) -> list[dict[str, str]]:
    """Backward-compatible dict action extraction for existing callers/tests."""
    return [action.model_dump(mode="json") for action in extract_action_items(report_md, max_items=max_items)]


def extract_action_items(
    report_md: str,
    claims: list[ReportClaim] | None = None,
    *,
    max_items: int = 6,
) -> list[ActionItem]:
    """Extract explicit next-action/recommendation bullets from the report."""
    items: list[ActionItem] = []
    claims = claims or []
    in_action_section = False
    for raw in report_md.splitlines():
        line = raw.strip()
        lower = line.lower()
        if line.startswith("#"):
            in_action_section = _contains_any(lower, ACTION_TOKENS)
            continue
        if not in_action_section and not _contains_any(lower, ACTION_TOKENS):
            continue
        if not line.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            continue
        text = line.lstrip("-*0123456789. ").strip()
        if len(text) < 6:
            continue
        linked_claims = _link_actions_to_claims(text, claims)
        evidence_ids = list(dict.fromkeys(eid for claim in linked_claims for eid in claim.evidence_ids))
        action = ActionItem(
            text=text[:220],
            priority=_action_priority(text),
            owner_hint=_owner_hint(text),
            expected_impact=_expected_impact(text),
            effort=_effort_hint(text),
            due_hint=_due_hint(text),
            supporting_claim_ids=[claim.id for claim in linked_claims],
            evidence_ids=evidence_ids,
        )
        items.append(action)
        for claim in linked_claims:
            claim.supporting_action_ids.append(action.id)
        if len(items) >= max_items:
            break
    return items


def build_report_plan(
    intent: ReportIntent,
    claims: list[ReportClaim],
    actions: list[ActionItem],
) -> ReportPlan:
    """Create an audience-specific report plan from structured evidence objects."""
    template = SECTION_TEMPLATES.get(intent.audience, SECTION_TEMPLATES["analyst"])
    sections: list[ReportSection] = []
    for role, title, preferred_blocks in template:
        section_claims = [claim.id for claim in claims if _claim_belongs_to_section(claim, role)]
        section_actions = [action.id for action in actions] if role == "actions" else []
        evidence_ids = list(dict.fromkeys(
            eid
            for claim in claims
            if claim.id in section_claims
            for eid in claim.evidence_ids
        ))
        if role == "actions":
            evidence_ids = list(dict.fromkeys(eid for action in actions for eid in action.evidence_ids))
        sections.append(ReportSection(
            id=f"section_{role}",
            role=role,
            title=title,
            claim_ids=section_claims,
            action_ids=section_actions,
            evidence_ids=evidence_ids,
            preferred_blocks=preferred_blocks,
            evidence_budget=EVIDENCE_BUDGETS.get(intent.audience, EVIDENCE_BUDGETS["analyst"]).get("primary_blocks"),
        ))

    return ReportPlan(
        audience=intent.audience,
        format=intent.format,
        depth=intent.depth,
        visual_density=intent.visual_density,
        sections=sections,
        evidence_budget=EVIDENCE_BUDGETS.get(intent.audience, EVIDENCE_BUDGETS["analyst"]),
        renderer_notes=[
            "Render sections in plan order.",
            "Prefer primary evidence in the main flow and move appendix evidence behind the main narrative.",
        ],
    )


def apply_report_plan_to_blocks(blocks: list[ArtifactBlock], plan: ReportPlan) -> list[ArtifactBlock]:
    """Assign section roles and apply a simple evidence budget to the reading flow."""
    claim_to_section: dict[str, str] = {}
    action_to_section: dict[str, str] = {}
    for section in plan.sections:
        for claim_id in section.claim_ids:
            claim_to_section[claim_id] = section.role
        for action_id in section.action_ids:
            action_to_section[action_id] = section.role

    primary_seen = 0
    primary_budget = plan.evidence_budget.get("primary_blocks", 12)
    appendix_budget = plan.evidence_budget.get("appendix_tables", 6)
    appendix_seen = 0

    for block in blocks:
        if block.claim_ids:
            block.section_role = claim_to_section.get(block.claim_ids[0], block.section_role)
        if block.action_ids:
            block.section_role = action_to_section.get(block.action_ids[0], "actions")
        if block.type == ArtifactBlockType.next_action_list:
            block.section_role = "actions"

        if block.evidence_priority == "primary":
            primary_seen += 1
            if primary_seen > primary_budget:
                block.evidence_priority = "appendix"
        elif block.evidence_priority == "appendix" and block.type == ArtifactBlockType.table:
            appendix_seen += 1
            if appendix_seen > appendix_budget:
                block.evidence_priority = "hidden"
    return blocks


def classify_claim_type(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, RECOMMENDATION_TOKENS):
        return "recommendation"
    if _contains_any(lower, RISK_TOKENS):
        return "risk"
    if _contains_any(lower, FORECAST_TOKENS):
        return "forecast"
    if _contains_any(lower, DIAGNOSIS_TOKENS):
        return "diagnosis"
    return "fact"


def classify_claim_impact(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, HIGH_IMPACT_TOKENS):
        return "high"
    if _contains_any(lower, LOW_IMPACT_TOKENS):
        return "low"
    return "medium"


def classify_time_horizon(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, LONG_TERM_TOKENS):
        return "long_term"
    if _contains_any(lower, SHORT_TERM_TOKENS):
        return "short_term"
    return "now"


def extract_metric_refs(text: str) -> list[str]:
    candidates = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", text)
    stopwords = {"the", "and", "for", "with", "from", "this", "that", "should", "action"}
    return list(dict.fromkeys(c for c in candidates if c.lower() not in stopwords))[:8]


def _claim_belongs_to_section(claim: ReportClaim, role: str) -> bool:
    if role in {"summary", "key_findings", "findings"}:
        return claim.claim_type in {"fact", "diagnosis", "forecast"}
    if role in {"risks", "caveats", "anomalies"}:
        return claim.claim_type == "risk"
    if role in {"variance", "diagnosis", "funnel"}:
        return claim.claim_type in {"diagnosis", "fact"}
    if role == "actions":
        return claim.claim_type == "recommendation"
    if role in {"scope", "method"}:
        return claim.claim_type == "fact"
    return False


def _link_actions_to_claims(text: str, claims: list[ReportClaim]) -> list[ReportClaim]:
    action_tokens = _tokenize(text)
    scored: list[tuple[int, ReportClaim]] = []
    for claim in claims:
        score = len(action_tokens & _tokenize(claim.text))
        if claim.claim_type == "recommendation":
            score += 1
        if score > 0:
            scored.append((score, claim))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [claim for _, claim in scored[:2]]


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token.lower() in text for token in tokens)


def _first_useful_statement(markdown: str) -> str:
    for raw in markdown.splitlines():
        clean = raw.strip().strip("#-* ")
        if not clean or len(clean) < 10:
            continue
        if clean.lower().startswith(("table", "chart", "source", "数据来源", "附录")):
            continue
        if "|" in clean and "---" in clean:
            continue
        parts = re.split(r"(?<=[。.!?])\s+", clean, maxsplit=1)
        return parts[0][:220]
    return ""


def _action_priority(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("低", "low", "optional")):
        return "low"
    if any(token in lower for token in ("立即", "高", "high", "urgent", "critical", "优先")):
        return "high"
    return "medium"


def _owner_hint(text: str) -> str | None:
    match = re.search(r"(?:owner|负责人|责任人)[:：]\s*([^,，。;；]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip()[:80] if match else None


def _expected_impact(text: str) -> str | None:
    lower = text.lower()
    if any(token in lower for token in ("提升", "increase", "improve", "增长")):
        return "increase_or_improve"
    if any(token in lower for token in ("降低", "reduce", "下降", "控制")):
        return "reduce_or_control"
    return None


def _effort_hint(text: str) -> str | None:
    lower = text.lower()
    if any(token in lower for token in ("轻量", "快速", "low effort", "quick")):
        return "low"
    if any(token in lower for token in ("复杂", "长期", "heavy", "large")):
        return "high"
    return None


def _due_hint(text: str) -> str | None:
    match = re.search(r"(本周|下周|本月|下月|\d+\s*天内|\d+\s*周内)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff_]+", text.lower()) if len(token) >= 2}
