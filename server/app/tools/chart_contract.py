"""Chart contract — canonical types, intents, and validation rules.

Mirrors the Codex Data Analytics plugin chart contract for:
- Chart type ↔ intent compatibility
- Mixed-scale detection (ratio >= 25:1)
- Mixed-metric detection (different measures on same axis)
- Single-series vs multi-series classification
- Intent-driven chart spec normalization for visual_report artifacts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_CHART_TYPES: set[str] = {
    "area", "bar", "boxPlot", "funnel", "heatmap", "histogram",
    "horizontalBar", "horizontalStackedBar", "horizontalStackedBar100",
    "leaderboard", "line", "pie", "scatter", "sparkline",
    "stackedArea", "stackedBar", "stackedBar100", "waterfall",
}

# File-based chart output types. Used across orchestrator, manifest builder,
# execution runner, and validation to classify output artifacts consistently.
FILE_CHART_TYPES: frozenset[str] = frozenset({"png", "jpg", "jpeg", "svg", "html", "plotly"})

ALLOWED_CHART_INTENTS: set[str] = {
    "comparison", "composition", "decomposition",
    "distribution", "funnel", "lookup",
    "relationship", "status", "trend",
}

INTENT_COMPATIBLE_CHART_TYPES: dict[str, set[str]] = {
    "comparison": {"bar", "horizontalBar", "leaderboard", "scatter"},
    "composition": {
        "horizontalStackedBar", "horizontalStackedBar100",
        "pie", "stackedArea", "stackedBar", "stackedBar100",
    },
    "decomposition": {"bar", "horizontalBar", "waterfall"},
    "distribution": {"boxPlot", "histogram"},
    "funnel": {"bar", "funnel", "horizontalBar"},
    "lookup": {"leaderboard"},
    "relationship": {"heatmap", "scatter"},
    "status": {"bar", "horizontalBar", "sparkline"},
    "trend": {"area", "bar", "line", "sparkline", "stackedArea"},
}

RECOMMENDED_CHART_TYPE_BY_INTENT: dict[str, str] = {
    "comparison": "horizontalBar",
    "composition": "stackedBar100",
    "decomposition": "waterfall",
    "distribution": "histogram",
    "funnel": "funnel",
    "lookup": "leaderboard",
    "relationship": "scatter",
    "status": "bar",
    "trend": "line",
}

SINGLE_SERIES_CHART_TYPES: set[str] = {
    "funnel", "histogram", "leaderboard", "pie", "sparkline", "waterfall",
}

INTRINSIC_MULTI_SERIES_CHART_TYPES: set[str] = {
    "boxPlot", "heatmap",
    "horizontalStackedBar", "horizontalStackedBar100",
    "stackedArea", "stackedBar", "stackedBar100",
}

LEADERBOARD_MAX_ROWS = 8
MIXED_SCALE_SERIES_RATIO = 25

MIXED_METRIC_AXIS_MARKERS = (
    "kpi", "measure", "metric",
)
MIXED_METRIC_CHANGE_FIELD_MARKERS = (
    "change_pct", "delta_pct", "movement_pct",
    "wow_change", "wow_pct", "week_over_week",
    "week_over_week_change", "week_over_week_pct", "w_w_change",
)

INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trend", ("trend", "time", "date", "daily", "weekly", "monthly", "quarter", "year", "同比", "环比", "趋势", "时间", "月", "周", "日")),
    ("ranking", ("top", "bottom", "rank", "leader", "ranking", "排行", "榜", "前", "后")),
    ("composition", ("share", "mix", "composition", "ratio", "percent", "结构", "占比", "份额", "构成")),
    ("decomposition", ("bridge", "waterfall", "driver", "contribution", "breakdown", "拆解", "归因", "贡献", "驱动")),
    ("distribution", ("distribution", "histogram", "bucket", "bins", "box", "分布", "区间")),
    ("relationship", ("correlation", "scatter", "relationship", "vs", "versus", "相关", "关系")),
    ("funnel", ("funnel", "conversion", "stage", "漏斗", "转化")),
)


@dataclass(frozen=True)
class ChartValidationResult:
    valid: bool
    error: str = ""
    warning: str = ""
    details: dict[str, Any] | None = None


def chart_type_valid(chart_type: str) -> bool:
    return chart_type in SUPPORTED_CHART_TYPES


def chart_intent_valid(intent: str) -> bool:
    return intent in ALLOWED_CHART_INTENTS or intent == ""


def compatible_chart_types_for_intent(intent: str) -> list[str]:
    """Return deterministic compatible chart types for a known intent."""
    return sorted(INTENT_COMPATIBLE_CHART_TYPES.get(intent, set()))


def recommended_chart_type_for_intent(intent: str, fallback: str = "bar") -> str:
    """Pick the preferred chart type for an intent, keeping the fallback valid when possible."""
    if not intent or intent not in ALLOWED_CHART_INTENTS:
        return fallback if fallback in SUPPORTED_CHART_TYPES else "bar"
    if fallback in INTENT_COMPATIBLE_CHART_TYPES.get(intent, set()):
        return fallback
    return RECOMMENDED_CHART_TYPE_BY_INTENT.get(intent, fallback if fallback in SUPPORTED_CHART_TYPES else "bar")


def infer_chart_intent(spec: dict[str, Any], default: str = "comparison") -> str:
    """Infer a chart intent from title/name/fields when the LLM omitted it."""
    explicit = str(spec.get("intent") or "").strip()
    if explicit in ALLOWED_CHART_INTENTS:
        return explicit

    haystack = " ".join(
        str(spec.get(key) or "")
        for key in ("name", "title", "description", "x_field", "x", "x_axis", "y_field", "y_axis")
    ).lower()
    y_fields = spec.get("y_fields") or spec.get("fields") or []
    if isinstance(y_fields, list):
        haystack += " " + " ".join(str(field).lower() for field in y_fields)

    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return "lookup" if intent == "ranking" else intent

    return default if default in ALLOWED_CHART_INTENTS else "comparison"


def normalize_chart_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize an LLM chart spec into the canonical visual_report contract.

    This does not invent data. It only standardizes names, intent, type and
    compatible type metadata so the manifest builder and validators can make
    consistent decisions.
    """
    normalized = dict(spec or {})
    raw_type = normalized.get("chart_type") or normalized.get("type") or "bar"
    chart_type = str(raw_type)
    if chart_type == "stacked bar":
        chart_type = "stackedBar"
    if chart_type == "box plot":
        chart_type = "boxPlot"
    if chart_type not in SUPPORTED_CHART_TYPES:
        chart_type = "bar"

    intent = infer_chart_intent({**normalized, "chart_type": chart_type})
    chart_type = recommended_chart_type_for_intent(intent, chart_type)

    normalized["chart_type"] = chart_type
    normalized["intent"] = intent
    normalized["compatible_types"] = compatible_chart_types_for_intent(intent)
    if "x" in normalized and "x_field" not in normalized:
        normalized["x_field"] = normalized["x"]
    if "x_axis" in normalized and "x_field" not in normalized:
        normalized["x_field"] = normalized["x_axis"]
    if "y" in normalized and "y_fields" not in normalized:
        normalized["y_fields"] = [normalized["y"]]
    if "y_axis" in normalized and "y_fields" not in normalized:
        normalized["y_fields"] = [normalized["y_axis"]]
    return normalized


def normalize_chart_specs(chart_specs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [normalize_chart_spec(spec) for spec in chart_specs or [] if isinstance(spec, dict)]


def intent_compatible_with_type(intent: str, chart_type: str) -> bool:
    if not intent or intent not in ALLOWED_CHART_INTENTS:
        return True
    allowed = INTENT_COMPATIBLE_CHART_TYPES.get(intent, set())
    return chart_type in allowed


def is_single_series_chart(chart_type: str) -> bool:
    return chart_type in SINGLE_SERIES_CHART_TYPES


def validate_chart_type(chart_type: str) -> ChartValidationResult:
    if not chart_type:
        return ChartValidationResult(valid=False, error="Chart type is required")
    if chart_type not in SUPPORTED_CHART_TYPES:
        return ChartValidationResult(
            valid=False,
            error=f"Unsupported chart type: {chart_type}",
            details={"supported": sorted(SUPPORTED_CHART_TYPES)},
        )
    return ChartValidationResult(valid=True)


def validate_chart_intent(intent: str, chart_type: str) -> ChartValidationResult:
    if intent and intent not in ALLOWED_CHART_INTENTS:
        return ChartValidationResult(
            valid=False,
            error=f"Unknown chart intent: {intent}",
            details={"allowed": sorted(ALLOWED_CHART_INTENTS)},
        )
    if intent and not intent_compatible_with_type(intent, chart_type):
        compatible = sorted(INTENT_COMPATIBLE_CHART_TYPES.get(intent, set()))
        return ChartValidationResult(
            valid=False,
            error=f"Chart type '{chart_type}' is not compatible with intent '{intent}'",
            details={"compatible_types": compatible},
        )
    return ChartValidationResult(valid=True)


def detect_mixed_scale(values: list[float]) -> ChartValidationResult:
    if len(values) < 2:
        return ChartValidationResult(valid=True)
    abs_vals = [abs(v) for v in values if v != 0]
    if len(abs_vals) < 2:
        return ChartValidationResult(valid=True)
    ratio = max(abs_vals) / min(abs_vals)
    if ratio >= MIXED_SCALE_SERIES_RATIO:
        return ChartValidationResult(
            valid=False,
            error=f"Mixed scale detected: max/min ratio {ratio:.0f} >= {MIXED_SCALE_SERIES_RATIO}",
            details={"max": max(abs_vals), "min": min(abs_vals), "ratio": ratio},
        )
    return ChartValidationResult(valid=True)


def detect_mixed_metric(
    field_names: list[str],
    values: list[float],
) -> ChartValidationResult:
    issues = []
    for name in field_names:
        name_lower = name.lower()
        for marker in MIXED_METRIC_AXIS_MARKERS:
            if marker in name_lower:
                issues.append(f"Field '{name}' contains metric marker '{marker}'")
                break
        for marker in MIXED_METRIC_CHANGE_FIELD_MARKERS:
            if marker in name_lower:
                issues.append(f"Field '{name}' is a change/percentage metric; avoid mixing with absolute values")
                break
    if issues:
        return ChartValidationResult(
            valid=False,
            error="Mixed metric fields detected on same axis",
            details={"issues": issues},
        )
    return ChartValidationResult(valid=True)


def validate_chart(
    chart_type: str,
    intent: str = "",
    y_fields: list[str] | None = None,
    y_values: list[float] | None = None,
) -> list[ChartValidationResult]:
    results: list[ChartValidationResult] = []

    type_result = validate_chart_type(chart_type)
    results.append(type_result)
    if not type_result.valid:
        return results

    intent_result = validate_chart_intent(intent, chart_type)
    results.append(intent_result)

    if y_values and len(y_values) >= 2:
        scale_result = detect_mixed_scale(y_values)
        results.append(scale_result)

    if y_fields and len(y_fields) > 1:
        metric_result = detect_mixed_metric(y_fields, y_values or [])
        results.append(metric_result)

    return results
