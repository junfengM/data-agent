"""Lightweight analysis-intent inference for LLM planning.

The goal is not to replace the LLM planner. It gives the planner a stable,
pre-analysis interpretation of the user's request so candidate angles and
execution steps are anchored before the report is written.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.models.schemas import DatasetProfile, ProjectContext


TASK_TOKENS: dict[str, tuple[str, ...]] = {
    "diagnosis": ("原因", "根因", "为什么", "诊断", "driver", "root cause", "why"),
    "monitoring": ("看板", "监控", "日报", "周报", "月报", "dashboard", "monitor", "overview"),
    "forecasting": ("预测", "预计", "未来", "forecast", "predict", "projection"),
    "comparison": ("对比", "比较", "vs", "versus", "compare", "difference"),
    "segmentation": ("分群", "分层", "细分", "segment", "cohort", "region", "channel"),
    "data_quality": ("口径", "缺失", "异常值", "数据质量", "quality", "missing", "null"),
    "reporting": ("报告", "汇报", "总结", "复盘", "report", "summary", "review"),
}

AUDIENCE_TOKENS: dict[str, tuple[str, ...]] = {
    "executive": ("管理层", "老板", "经营", "高层", "executive", "management", "board"),
    "finance": ("财务", "预算", "收入", "成本", "利润", "毛利", "finance", "revenue", "cost", "margin"),
    "ops": ("运营", "异常", "告警", "处理", "优先级", "ops", "operation", "incident"),
    "product": ("产品", "留存", "转化", "漏斗", "product", "retention", "conversion", "funnel"),
    "analyst": ("分析", "明细", "拆解", "analyst", "analysis", "detail"),
}

OUTPUT_TOKENS: dict[str, tuple[str, ...]] = {
    "dashboard": ("看板", "dashboard", "监控", "速览"),
    "action_plan": ("建议", "行动", "下一步", "action", "recommend"),
    "deep_dive": ("深入", "详细", "拆解", "诊断", "deep dive", "root cause"),
    "report": ("报告", "总结", "汇报", "report", "summary"),
}

METRIC_HINTS = (
    "revenue", "gmv", "sales", "order", "orders", "profit", "margin", "cost",
    "retention", "conversion", "active", "users", "aov", "收入", "销售", "订单",
    "利润", "毛利", "成本", "留存", "转化", "用户", "客单价",
)

DIMENSION_HINTS = (
    "date", "month", "week", "day", "region", "city", "country", "channel",
    "category", "sku", "product", "customer", "store", "segment", "cohort",
    "日期", "月份", "周", "区域", "城市", "渠道", "品类", "商品", "客户", "门店", "分群",
)


def infer_analysis_intent(
    question: str,
    profiles: list[DatasetProfile],
    project_contexts: list[ProjectContext] | None = None,
    ad_hoc_context: str | None = None,
) -> dict[str, Any]:
    """Infer a stable pre-analysis intent from request text and dataset metadata."""
    context_text = " ".join(
        [question or "", ad_hoc_context or ""]
        + [f"{ctx.title} {ctx.body}" for ctx in project_contexts or []]
    )
    text = context_text.lower()
    rationale: list[str] = []

    task_type = _first_matching_key(text, TASK_TOKENS) or "exploratory"
    if task_type != "exploratory":
        rationale.append(f"task_tokens:{task_type}")

    audience = _first_matching_key(text, AUDIENCE_TOKENS) or "analyst"
    if audience != "analyst" or _contains_any(text, AUDIENCE_TOKENS["analyst"]):
        rationale.append(f"audience_tokens:{audience}")

    expected_output = _first_matching_key(text, OUTPUT_TOKENS) or _default_output(task_type)
    if expected_output:
        rationale.append(f"output:{expected_output}")

    primary_metrics = _extract_columns(question, profiles, METRIC_HINTS, max_items=6)
    dimensions = _extract_columns(question, profiles, DIMENSION_HINTS, max_items=8)

    if primary_metrics:
        rationale.append("metric_columns_matched")
    if dimensions:
        rationale.append("dimension_columns_matched")

    ambiguities = _ambiguities(question, profiles, primary_metrics, dimensions)
    evidence_level = "high" if profiles else "low"
    if task_type in {"diagnosis", "forecasting", "comparison"}:
        evidence_level = "high" if profiles else "medium"

    confidence = 0.45
    confidence += 0.15 if task_type != "exploratory" else 0.0
    confidence += 0.10 if audience != "analyst" else 0.0
    confidence += 0.15 if primary_metrics else 0.0
    confidence += 0.10 if dimensions else 0.0
    confidence -= 0.10 if ambiguities else 0.0
    confidence = round(max(0.2, min(confidence, 0.9)), 2)

    return {
        "task_type": task_type,
        "decision_goal": _decision_goal(task_type, question),
        "audience": audience,
        "time_scope": _time_scope(text),
        "primary_metrics": primary_metrics,
        "dimensions": dimensions,
        "expected_output": expected_output,
        "evidence_level": evidence_level,
        "ambiguities": ambiguities,
        "confidence": confidence,
        "rationale": rationale,
    }


def format_analysis_intent_for_prompt(intent: dict[str, Any]) -> str:
    """Render intent as compact prompt context for the LLM."""
    lines = [
        "## Pre-analysis Intent",
        "",
        "Use this deterministic interpretation to anchor candidate angles before writing conclusions.",
        f"- task_type: {intent.get('task_type')}",
        f"- audience: {intent.get('audience')}",
        f"- expected_output: {intent.get('expected_output')}",
        f"- evidence_level: {intent.get('evidence_level')}",
        f"- decision_goal: {intent.get('decision_goal')}",
        f"- time_scope: {intent.get('time_scope')}",
        f"- primary_metrics: {', '.join(intent.get('primary_metrics') or []) or 'unknown'}",
        f"- dimensions: {', '.join(intent.get('dimensions') or []) or 'unknown'}",
    ]
    ambiguities = intent.get("ambiguities") or []
    if ambiguities:
        lines.append(f"- ambiguities: {'; '.join(ambiguities)}")
    return "\n".join(lines)


def _first_matching_key(text: str, mapping: dict[str, tuple[str, ...]]) -> str | None:
    for key, tokens in mapping.items():
        if _contains_any(text, tokens):
            return key
    return None


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token.lower() in text for token in tokens)


def _default_output(task_type: str) -> str:
    if task_type == "monitoring":
        return "dashboard"
    if task_type in {"diagnosis", "comparison", "forecasting", "segmentation"}:
        return "deep_dive"
    return "report"


def _extract_columns(question: str, profiles: list[DatasetProfile], hints: tuple[str, ...], *, max_items: int) -> list[str]:
    q = (question or "").lower()
    matched: list[str] = []
    for profile in profiles:
        for col in profile.columns:
            name = col.name
            lower = name.lower()
            if lower in q or any(hint in lower for hint in hints):
                matched.append(name)
    return list(dict.fromkeys(matched))[:max_items]


def _ambiguities(
    question: str,
    profiles: list[DatasetProfile],
    metrics: list[str],
    dimensions: list[str],
) -> list[str]:
    ambiguities: list[str] = []
    if profiles and not metrics:
        ambiguities.append("No obvious metric column matched the question; planner must inspect numeric columns before ranking angles.")
    if profiles and not dimensions:
        ambiguities.append("No obvious dimension/time column matched the question; planner must identify useful cuts from data profile.")
    if not profiles:
        ambiguities.append("No dataset profile is available; conclusions must stay caveated unless external evidence is supplied.")
    if len((question or "").strip()) < 12:
        ambiguities.append("Question is terse; prioritize exploratory breadth before deep-dive selection.")
    return ambiguities[:4]


def _decision_goal(task_type: str, question: str) -> str:
    if task_type == "diagnosis":
        return "Identify the most likely drivers and quantify their contribution."
    if task_type == "monitoring":
        return "Surface current status, anomalies, and priority follow-ups."
    if task_type == "forecasting":
        return "Estimate future movement and explain assumptions or uncertainty."
    if task_type == "comparison":
        return "Compare groups or periods and explain material differences."
    if task_type == "segmentation":
        return "Find meaningful segments that change decisions or prioritization."
    if task_type == "data_quality":
        return "Assess whether the data is reliable enough for downstream analysis."
    if task_type == "reporting":
        return "Produce an answer-first summary with evidence and next steps."
    return f"Explore the data for decision-relevant findings related to: {question[:120]}"


def _time_scope(text: str) -> str:
    if any(token in text for token in ("本周", "week", "weekly")):
        return "weekly"
    if any(token in text for token in ("本月", "月报", "month", "monthly")):
        return "monthly"
    if any(token in text for token in ("季度", "quarter", "quarterly")):
        return "quarterly"
    if any(token in text for token in ("年", "year", "annual")):
        return "annual"
    if any(token in text for token in ("今天", "昨日", "昨天", "today", "yesterday")):
        return "daily"
    return "unspecified"
