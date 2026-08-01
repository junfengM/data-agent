from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.models.schemas import DatasetProfile, ModelConfigSummary, ProjectContext


ROLE_VALUES = {"metric", "dimension", "time", "identifier", "text", "flag", "ignore"}
AGGREGATION_VALUES = {
    "sum", "avg", "weighted_avg", "count", "count_distinct", "min", "max", "latest", "group_by", "none", "unknown"
}

# ── ProfileLike: accept either DatasetProfile or a workbook dict ──────────

ProfileLike = DatasetProfile | dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SemanticColumnDraft(BaseModel):
    source_column: str
    display_name: str = ""
    role: str = "ignore"
    semantic_type: str = "unknown"
    default_aggregation: str = "unknown"
    grain: str = "row"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    confirmed: bool = False
    user_modified: bool = False
    include_in_layer: bool = True
    source_table: str = ""
    sheet_name: str = ""


class SuggestedMetricDraft(BaseModel):
    name: str
    formula: str
    source_columns: list[str] = Field(default_factory=list)
    aggregation: str = "unknown"
    grain: str = "row"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    needs_user_confirmation: bool = True
    source_table: str = ""
    sheet_name: str = ""


class SemanticDraft(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    dataset_id: str
    filename: str
    status: str = "draft"
    source: str = "heuristic"
    llm_model: str | None = None
    columns: list[SemanticColumnDraft] = Field(default_factory=list)
    suggested_metrics: list[SuggestedMetricDraft] = Field(default_factory=list)
    questions_for_user: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class SemanticDraftRequest(BaseModel):
    use_llm: bool = True
    model_config_id: str | None = None


class SemanticDraftUpdate(BaseModel):
    columns: list[SemanticColumnDraft] | None = None
    suggested_metrics: list[SuggestedMetricDraft] | None = None
    questions_for_user: list[str] | None = None
    warnings: list[str] | None = None


# ── Profile normalization ─────────────────────────────────────────────────

def _normalize_profile(profile: ProfileLike) -> dict[str, Any]:
    """Convert any profile into a uniform workbook dict.

    The returned dict always has:
      - "filename", "dataset_id", "format", "warnings", "sheets", "columns"
    Each sheet has: "sheet_name", "source_table", "row_count", "columns"
    Every column in every sheet has: "name", "source_table", "sheet_name"
    The top-level "columns" is a flat list of ALL columns across sheets.
    """
    if isinstance(profile, DatasetProfile):
        sheets = [{
            "sheet_name": "",
            "source_table": profile.filename,
            "row_count": profile.row_count,
            "columns": [
                {
                    **col.model_dump(),
                    "source_table": profile.filename,
                    "sheet_name": "",
                }
                for col in profile.columns
            ],
        }]
        flat_columns = [
            {**col.model_dump(), "source_table": profile.filename, "sheet_name": ""}
            for col in profile.columns
        ]
        return {
            "filename": profile.filename,
            "dataset_id": profile.dataset_id,
            "format": "single_table",
            "warnings": list(profile.warnings),
            "sheets": sheets,
            "columns": flat_columns,
        }

    result: dict[str, Any] = dict(profile)
    sheets: list[dict[str, Any]] = result.get("sheets", [])
    flat_columns: list[dict[str, Any]] = []
    for sheet in sheets:
        filename = str(result.get("filename", ""))
        sheet_name = str(sheet.get("sheet_name", ""))
        source_table = str(sheet.get("source_table", filename))
        row_count = int(sheet.get("row_count", 0))
        for col in sheet.get("columns", []):
            col = dict(col)
            col.setdefault("name", str(col.get("source_column", col.get("name", ""))))
            col.setdefault("source_table", source_table)
            col.setdefault("sheet_name", sheet_name)
            col.setdefault("row_count", row_count)
            flat_columns.append(col)
    result["columns"] = flat_columns
    result.setdefault("warnings", [])
    result.setdefault("format", result.get("sheet_count") and "excel" or "csv")
    return result


# ── Column key helpers for multi-sheet disambiguation ─────────────────────

def _column_key(source_table: str, source_column: str) -> str:
    """Unique key for a column within a workbook."""
    return f"{source_table}::{source_column}"


def _column_meta_by_key(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map {source_table::name: column_meta} for all columns."""
    result: dict[str, dict[str, Any]] = {}
    for col in profile.get("columns", []):
        st = str(col.get("source_table", ""))
        name = str(col.get("name", ""))
        key = _column_key(st, name)
        result[key] = col
    return result


def _column_keys_by_name(profile: dict[str, Any]) -> dict[str, list[str]]:
    """Map {column_name: [source_table::name, ...]} for disambiguation."""
    result: dict[str, list[str]] = {}
    for col in profile.get("columns", []):
        name = str(col.get("name", ""))
        key = _column_key(str(col.get("source_table", "")), name)
        result.setdefault(name, []).append(key)
    return result


def _resolve_column_key(
    source_column: str,
    source_table: str,
    sheet_name: str,
    column_meta: dict[str, dict[str, Any]],
    name_to_keys: dict[str, list[str]],
) -> str | None:
    """Resolve a logical column reference to a unique column key.

    Returns None if the reference is ambiguous or the column doesn't exist.
    """
    keys = name_to_keys.get(source_column, [])
    if not keys:
        return None

    if len(keys) == 1:
        return keys[0]

    for key in keys:
        meta = column_meta.get(key)
        if meta is None:
            continue
        if source_table and meta.get("source_table") == source_table:
            return key
        if sheet_name and meta.get("sheet_name") == sheet_name:
            return key

    return None


# ── Heuristic draft (supports ProfileLike) ───────────────────────────────

def infer_semantic_draft_heuristic(*, profile: ProfileLike, project_id: str) -> SemanticDraft:
    """Create a semantic draft from deterministic column profiling."""
    normalized = _normalize_profile(profile)
    columns = [
        _infer_column(column, column.get("row_count") or 0)
        for column in normalized["columns"]
    ]
    draft = SemanticDraft(
        project_id=project_id,
        dataset_id=normalized["dataset_id"],
        filename=normalized["filename"],
        columns=columns,
        source="heuristic",
        warnings=list(normalized.get("warnings", [])),
    )
    draft.suggested_metrics = _suggest_metrics_from_columns(columns)
    draft.questions_for_user = _questions_for_columns(columns)
    return validate_semantic_draft(draft, profile=normalized)


# ── LLM-assisted draft (supports ProfileLike) ────────────────────────────

async def infer_semantic_draft_with_llm(
    *,
    profile: ProfileLike,
    project_id: str,
    project_contexts: list[ProjectContext] | None = None,
    model_config: ModelConfigSummary | None = None,
    use_llm: bool = True,
) -> SemanticDraft:
    """Use the LLM to improve a semantic draft, then validate it."""
    normalized = _normalize_profile(profile)
    baseline = infer_semantic_draft_heuristic(profile=normalized, project_id=project_id)
    if not use_llm or model_config is None:
        if use_llm:
            baseline.warnings.append("LLM semantic inference skipped: no model configuration available.")
        return baseline

    api_key = os.getenv(model_config.api_key_env)
    if not api_key:
        baseline.warnings.append(f"LLM semantic inference skipped: missing ${model_config.api_key_env}.")
        return baseline

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=model_config.base_url)
        response = await client.chat.completions.create(
            model=model_config.model,
            messages=[
                {"role": "system", "content": _SEMANTIC_INFERENCE_SYSTEM_PROMPT},
                {"role": "user", "content": _build_llm_prompt(normalized, baseline, project_contexts or [])},
            ],
            temperature=model_config.temperature or 0.1,
            max_tokens=min(model_config.max_tokens or 4096, 4096),
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        merged = _merge_llm_payload(baseline, payload)
        merged.source = "llm_assisted"
        merged.llm_model = model_config.id
        merged.updated_at = _now_iso()
        return validate_semantic_draft(merged, profile=normalized)
    except Exception as exc:  # pragma: no cover - depends on external LLM availability
        baseline.warnings.append(f"LLM semantic inference failed; heuristic draft used. Error: {exc}")
        return baseline


# ── Validation ────────────────────────────────────────────────────────────

def validate_semantic_draft(draft: SemanticDraft, profile: ProfileLike | None = None) -> SemanticDraft:
    """Apply hard guardrails after heuristic or LLM semantic inference."""
    normalized: dict[str, Any] | None = None
    column_meta: dict[str, dict[str, Any]] = {}
    name_to_keys: dict[str, list[str]] = {}

    if profile is not None:
        normalized = _normalize_profile(profile)
        column_meta = _column_meta_by_key(normalized)
        name_to_keys = _column_keys_by_name(normalized)

    validated: list[SemanticColumnDraft] = []

    for column in draft.columns:
        col_key = _resolve_column_key(
            column.source_column,
            column.source_table,
            column.sheet_name,
            column_meta,
            name_to_keys,
        )
        if column_meta and col_key is None:
            if column.source_column not in name_to_keys:
                draft.warnings.append(f"Dropped semantic inference for unknown column: {column.source_column}")
            else:
                draft.warnings.append(
                    f"Dropped ambiguous column '{column.source_column}' — "
                    f"appears in multiple sheets without source_table/sheet_name."
                )
            continue

        c = column.model_copy(deep=True)
        c.role = c.role if c.role in ROLE_VALUES else "ignore"
        c.default_aggregation = c.default_aggregation if c.default_aggregation in AGGREGATION_VALUES else "unknown"
        c.confidence = max(0.0, min(1.0, c.confidence))
        if not c.display_name:
            c.display_name = c.source_column

        if col_key and col_key in column_meta:
            meta = column_meta[col_key]
            if not c.source_table:
                c.source_table = str(meta.get("source_table", ""))
            if not c.sheet_name:
                c.sheet_name = str(meta.get("sheet_name", ""))

        lower_name = c.source_column.lower()
        if c.role == "identifier" and c.default_aggregation in {"sum", "avg", "weighted_avg", "min", "max"}:
            c.default_aggregation = "count_distinct"
            c.caveats.append("Identifier fields are guarded against numeric aggregation.")
        if _is_rate_like(lower_name, c.semantic_type) and c.default_aggregation == "sum":
            c.default_aggregation = "avg"
            c.caveats.append("Rate/ratio fields should not be summed; confirm whether weighted average is required.")
        if c.role in {"dimension", "time", "flag"} and c.default_aggregation in {"sum", "avg", "weighted_avg"}:
            c.default_aggregation = "group_by"
        if c.role == "text" and c.default_aggregation != "none":
            c.default_aggregation = "none"

        meta = column_meta.get(col_key) if col_key else None
        if meta and meta.get("null_pct", 0) > 20 and not any("null" in x.lower() or "空" in x for x in c.caveats):
            null_pct = meta.get("null_pct", 0)
            c.caveats.append(f"Column has {null_pct:.0f}% null values; confirm completeness before decision use.")
        c.caveats = _dedupe(c.caveats)
        validated.append(c)

    draft.columns = validated
    draft.suggested_metrics = _validate_suggested_metrics(
        draft.suggested_metrics,
        column_meta=column_meta,
        name_to_keys=name_to_keys,
    )
    if not draft.suggested_metrics:
        draft.suggested_metrics = _suggest_metrics_from_columns(validated)
    draft.questions_for_user = _dedupe(draft.questions_for_user or _questions_for_columns(validated))
    draft.warnings = _dedupe(draft.warnings)
    draft.updated_at = _now_iso()
    return draft


# ── Layer payload conversion ──────────────────────────────────────────────

def semantic_draft_to_layer_payload(draft: SemanticDraft) -> dict[str, Any]:
    """Convert confirmed semantic draft fields into semantic-layer YAML payload."""
    metrics: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    source_columns: list[dict[str, str]] = []

    for c in draft.columns:
        source_table = (
            c.source_table
            or (f"{draft.filename}#{c.sheet_name}" if c.sheet_name else draft.filename)
        )
        source_columns.append({
            "name": c.source_column,
            "semantic_role": c.role,
            "semantic_type": c.semantic_type,
            "source_table": source_table,
            "sheet_name": c.sheet_name,
        })
        if not c.include_in_layer:
            continue
        if c.role == "metric":
            metrics.append({
                "name": c.display_name or c.source_column,
                "formula": _formula_for_column(c),
                "aggregation": c.default_aggregation,
                "grain": c.grain,
                "dimensions": [],
                "sources": [source_table],
                "source_column": c.source_column,
                "source_dataset": draft.filename,
                "source_table": source_table,
                "sheet_name": c.sheet_name,
                "semantic_type": c.semantic_type,
                "caveats": c.caveats,
                "confirmed_by": "user",
                "confidence": c.confidence,
                "provenance": {
                    "draft_id": draft.id,
                    "dataset_id": draft.dataset_id,
                    "source": draft.source,
                    "confirmed_at": _now_iso(),
                },
            })
        elif c.role in {"dimension", "time", "identifier", "flag"}:
            dimensions.append({
                "name": c.display_name or c.source_column,
                "type": c.semantic_type,
                "source_column": c.source_column,
                "source_table": source_table,
                "sheet_name": c.sheet_name,
                "grain": [c.grain] if c.role == "time" and c.grain else [],
                "description": "; ".join(c.evidence[:2]),
                "role": c.role,
                "confirmed_by": "user",
                "confidence": c.confidence,
                "caveats": c.caveats,
            })

    return {
        "metrics": metrics,
        "dimensions": dimensions,
        "sources": [{
            "id": draft.dataset_id,
            "name": draft.filename,
            "type": "file",
            "path": draft.dataset_id,
            "grain": "uploaded rows",
            "columns": source_columns,
        }],
        "caveats": [
            {"severity": "warning", "description": warning, "source": f"semantic_draft:{draft.id}"}
            for warning in draft.warnings
        ],
    }


# ── Column inference ──────────────────────────────────────────────────────

def _infer_column(column: dict[str, Any], row_count: int) -> SemanticColumnDraft:
    name = str(column.get("name", ""))
    lower = name.lower()
    dtype = str(column.get("dtype", "")).lower()
    unique_count = int(column.get("unique_count") or 0)
    null_pct = float(column.get("null_pct") or 0)
    samples = [str(v).lower() for v in column.get("sample_values", [])]
    source_table = str(column.get("source_table") or "")
    sheet_name = str(column.get("sheet_name") or "")
    evidence: list[str] = []
    caveats: list[str] = []

    def entry(role: str, semantic_type: str, agg: str, confidence: float, grain: str = "row") -> SemanticColumnDraft:
        if null_pct > 20:
            caveats.append(f"Column has {null_pct:.0f}% null values.")
        return SemanticColumnDraft(
            source_column=name,
            display_name=name,
            role=role,
            semantic_type=semantic_type,
            default_aggregation=agg,
            grain=grain,
            confidence=confidence,
            evidence=evidence.copy(),
            caveats=_dedupe(caveats),
            include_in_layer=role != "ignore",
            source_table=source_table,
            sheet_name=sheet_name,
        )

    if _contains_any(lower, ["date", "time", "day", "month", "year", "日期", "时间", "月份", "账期", "年", "月", "日"]):
        evidence.append("Column name suggests a temporal field.")
        return entry("time", "date/time", "group_by", 0.86, "inferred from values")
    if _contains_any(
        lower,
        ["id", "uuid", "编号", "单号", "卡号", "账号", "编码", "code", "主键", "uid", "user_id", "order_id"],
    ):
        evidence.append("Column name suggests an identifier.")
        return entry("identifier", "entity_id", "count_distinct", 0.9)
    if _looks_like_date_samples(samples):
        evidence.append("Sample values look like dates or periods.")
        return entry("time", "date/time", "group_by", 0.72, "inferred from values")
    if _contains_any(lower, ["rate", "ratio", "pct", "percent", "%", "率", "占比", "比例", "转化率", "cvr"]):
        evidence.append("Column name suggests a rate or ratio.")
        caveats.append("Confirm whether this should be weighted by a denominator field.")
        return entry("metric", "rate", "avg", 0.78)
    if _contains_any(lower, ["gmv", "amount", "revenue", "sales", "price", "cost", "fee", "金额", "销售额", "收入", "成本", "价格", "费用", "流水"]):
        evidence.append("Column name suggests an additive monetary amount.")
        caveats.append("Confirm currency, unit, tax, and refund treatment.")
        return entry("metric", "currency_amount", "sum", 0.82)
    if _contains_any(lower, ["count", "qty", "quantity", "num", "number", "数量", "单量", "件数", "次数"]):
        evidence.append("Column name suggests a count or quantity.")
        return entry("metric", "quantity", "sum", 0.75)
    if row_count and unique_count >= max(20, row_count * 0.8) and _is_numeric_dtype(dtype):
        evidence.append("High-cardinality numeric field; likely an identifier rather than a measure.")
        caveats.append("Confirm this is not a measurable numeric value before using it as an ID.")
        return entry("identifier", "entity_id", "count_distinct", 0.62)
    if _contains_any(lower, ["is_", "has_", "是否", "标记", "flag"]):
        evidence.append("Column name suggests a boolean or flag.")
        return entry("flag", "boolean", "group_by", 0.75)

    if _is_numeric_dtype(dtype):
        if _is_likely_business_dimension_name(lower) and unique_count and unique_count <= max(20, row_count * 0.2 if row_count else 20):
            evidence.append("Column name and low cardinality suggest a numeric business dimension.")
            caveats.append("Confirm this numeric-coded field should be grouped rather than aggregated.")
            return entry("dimension", "categorical", "group_by", 0.62)
        evidence.append("Column dtype is numeric.")
        caveats.append("Auto-inferred numeric metric; confirm business meaning and aggregation.")
        return entry("metric", "numeric_value", "sum", 0.55)

    dimension_threshold = max(100, row_count * 0.4 if row_count else 100)
    if _is_likely_business_dimension_name(lower):
        evidence.append("Column name suggests a business grouping/filter dimension.")
        if row_count and unique_count > row_count * 0.7:
            caveats.append("High-cardinality dimension candidate; confirm it is useful for grouping or filtering.")
            return entry("dimension", "categorical", "group_by", 0.56)
        return entry("dimension", "categorical", "group_by", 0.78)
    if unique_count and unique_count <= dimension_threshold:
        evidence.append("Low-to-moderate cardinality suggests a categorical dimension.")
        return entry("dimension", "categorical", "group_by", 0.70)
    if row_count and unique_count and unique_count < row_count * 0.7:
        evidence.append("Moderate-cardinality text field may be a business dimension.")
        caveats.append("Confirm whether this field should be used as a grouping or filter dimension.")
        return entry("dimension", "categorical", "group_by", 0.55)

    evidence.append("Free-text or high-cardinality non-numeric field.")
    return entry("text", "text", "none", 0.45)


# ── Suggested metrics ─────────────────────────────────────────────────────

def _suggest_metrics_from_columns(columns: list[SemanticColumnDraft]) -> list[SuggestedMetricDraft]:
    metrics: list[SuggestedMetricDraft] = []
    for c in columns:
        if c.role != "metric" or not c.include_in_layer:
            continue
        metrics.append(SuggestedMetricDraft(
            name=c.display_name or c.source_column,
            formula=_formula_for_column(c),
            source_columns=[c.source_column],
            aggregation=c.default_aggregation,
            grain=c.grain,
            confidence=c.confidence,
            caveats=c.caveats,
            needs_user_confirmation=True,
            source_table=c.source_table,
            sheet_name=c.sheet_name,
        ))
    return metrics[:20]


def _validate_suggested_metrics(
    metrics: list[SuggestedMetricDraft],
    *,
    column_meta: dict[str, dict[str, Any]],
    name_to_keys: dict[str, list[str]],
) -> list[SuggestedMetricDraft]:
    """Validate suggested metrics, resolving source_columns via source_table."""
    result: list[SuggestedMetricDraft] = []
    for metric in metrics:
        resolved_cols: list[str] = []
        resolved_sources: list[str] = []
        resolved_sheets: list[str] = []
        for col_name in metric.source_columns:
            key = _resolve_column_key(col_name, metric.source_table, metric.sheet_name, column_meta, name_to_keys)
            if key is not None:
                meta = column_meta.get(key)
                if meta:
                    resolved_cols.append(meta.get("name", col_name))
                    resolved_sources.append(str(meta.get("source_table", "")))
                    resolved_sheets.append(str(meta.get("sheet_name", "")))
        if not metric.name or not resolved_cols:
            continue
        m = metric.model_copy(deep=True)
        m.source_columns = resolved_cols
        m.aggregation = m.aggregation if m.aggregation in AGGREGATION_VALUES else "unknown"
        m.confidence = max(0.0, min(1.0, m.confidence))
        m.needs_user_confirmation = True
        if not m.source_table and resolved_sources and len(set(resolved_sources)) == 1:
            m.source_table = resolved_sources[0]
        if not m.sheet_name and resolved_sheets and len(set(resolved_sheets)) == 1:
            m.sheet_name = resolved_sheets[0]
        result.append(m)
    return result[:20]


# ── Questions ─────────────────────────────────────────────────────────────

def _questions_for_columns(columns: list[SemanticColumnDraft]) -> list[str]:
    questions: list[str] = []
    for c in columns:
        if c.role == "metric" and c.semantic_type == "currency_amount":
            questions.append(f"{c.display_name} 的单位、币种、税费和退款处理口径是什么？")
        if c.role == "metric" and c.semantic_type in {"rate", "ratio"}:
            questions.append(f"{c.display_name} 是否需要按分母字段加权，而不是直接平均？")
        if c.role == "metric" and c.confidence < 0.65:
            questions.append(f"{c.display_name} 是否确实是可聚合指标？默认聚合方式是否正确？")
        if c.role == "dimension" and c.confidence < 0.60:
            questions.append(f"{c.display_name} 是否应该作为分组/筛选维度？")
    return _dedupe(questions)[:12]


# ── LLM merge ─────────────────────────────────────────────────────────────

def _merge_llm_payload(baseline: SemanticDraft, payload: dict[str, Any]) -> SemanticDraft:
    """Merge LLM output into baseline, using source_table::source_column keys."""
    known: dict[str, SemanticColumnDraft] = {}
    for c in baseline.columns:
        known[_column_key(c.source_table, c.source_column)] = c

    merged_columns: list[SemanticColumnDraft] = []
    llm_seen_keys: set[str] = set()

    for item in payload.get("columns", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("source_column") or item.get("name") or "")
        llm_source_table = str(item.get("source_table") or "")
        llm_sheet_name = str(item.get("sheet_name") or "")

        resolved_key: str | None = None
        for key, col in known.items():
            if col.source_column != name:
                continue
            if key in llm_seen_keys:
                continue
            if llm_source_table and col.source_table == llm_source_table:
                resolved_key = key
                break
            if llm_sheet_name and col.sheet_name == llm_sheet_name:
                resolved_key = key
                break
            if not llm_source_table and not llm_sheet_name:
                matching = [k for k, c in known.items() if c.source_column == name]
                if len(matching) == 1:
                    resolved_key = key
                    break

        if resolved_key is None:
            continue

        base = known[resolved_key]
        llm_seen_keys.add(resolved_key)
        update = {
            **base.model_dump(),
            **{k: v for k, v in item.items() if v is not None},
            "source_column": name,
            "source_table": base.source_table,
            "sheet_name": base.sheet_name,
            "confirmed": False,
            "include_in_layer": bool(item.get("include_in_layer", base.include_in_layer)),
        }
        merged_columns.append(SemanticColumnDraft(**update))

    if merged_columns:
        changed = {_column_key(m.source_table, m.source_column) for m in merged_columns}
        baseline.columns = merged_columns + [
            c for c in baseline.columns
            if _column_key(c.source_table, c.source_column) not in changed
        ]

    if isinstance(payload.get("suggested_metrics"), list):
        metrics = []
        for item in payload["suggested_metrics"]:
            if isinstance(item, dict):
                try:
                    metrics.append(SuggestedMetricDraft(**item))
                except Exception:
                    continue
        if metrics:
            baseline.suggested_metrics = metrics
    if isinstance(payload.get("questions_for_user"), list):
        baseline.questions_for_user = [str(q) for q in payload["questions_for_user"] if str(q).strip()]
    if isinstance(payload.get("warnings"), list):
        baseline.warnings.extend(str(w) for w in payload["warnings"] if str(w).strip())
    return baseline


# ── LLM prompt ────────────────────────────────────────────────────────────

def _build_llm_prompt(profile: dict[str, Any], baseline: SemanticDraft, contexts: list[ProjectContext]) -> str:
    """Build LLM prompt from a normalized workbook profile dict."""
    context_payload = [{"kind": c.kind, "title": c.title, "body": c.body[:800]} for c in contexts[:6]]
    return json.dumps(
        {
            "task": "Improve the semantic draft for one uploaded dataset (may contain multiple sheets). Return JSON only.",
            "constraints": [
                "Do not invent columns.",
                "All outputs are draft suggestions; set confirmed=false.",
                "Prefer conservative confidence when business meaning is ambiguous.",
                "Actively identify business dimensions for grouping/filtering, including region, channel, category, customer segment, product, status, owner, department, campaign, store, brand, and other categorical fields.",
                "If a field may be a dimension but is ambiguous, keep it as dimension with lower confidence and add caveats instead of marking it as text.",
                "For rates/ratios, do not use sum; ask whether weighted average is needed.",
                "For identifiers, use count_distinct, not sum/avg.",
                "Every output column/metric must include source_table or sheet_name when present.",
                "Same-named columns across sheets must be disambiguated with source_table.",
                "Never mix columns from different sheets unless project_context explicitly defines a relationship.",
                "If unsure which sheet is the fact table, add a question_for_user.",
            ],
            "allowed_roles": sorted(ROLE_VALUES),
            "allowed_aggregations": sorted(AGGREGATION_VALUES),
            "project_context": context_payload,
            "dataset_profile": profile,
            "baseline_draft": baseline.model_dump(mode="json"),
            "required_shape": {
                "columns": [SemanticColumnDraft.model_json_schema()],
                "suggested_metrics": [SuggestedMetricDraft.model_json_schema()],
                "questions_for_user": ["string"],
                "warnings": ["string"],
            },
        },
        ensure_ascii=False,
    )


# ── Formula helper ────────────────────────────────────────────────────────

def _formula_for_column(column: SemanticColumnDraft) -> str:
    col = column.source_column
    agg = column.default_aggregation
    if agg == "sum":
        return f"SUM({col})"
    if agg in {"avg", "weighted_avg"}:
        return f"AVG({col})"
    if agg == "count":
        return f"COUNT({col})"
    if agg == "count_distinct":
        return f"COUNT_DISTINCT({col})"
    if agg == "min":
        return f"MIN({col})"
    if agg == "max":
        return f"MAX({col})"
    return f"{agg.upper()}({col})" if agg not in {"unknown", "none", "group_by"} else col


# ── Utility helpers ───────────────────────────────────────────────────────

def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _is_numeric_dtype(dtype: str) -> bool:
    return any(token in dtype for token in ["int", "float", "double", "decimal", "number"])


def _looks_like_date_samples(samples: list[str]) -> bool:
    if not samples:
        return False
    matches = 0
    for sample in samples[:5]:
        value = sample.strip()
        if re.match(r"^\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?(?:[T\s].*)?$", value):
            matches += 1
            continue
        if re.match(r"^\d{4}年\d{1,2}月(?:\d{1,2}日)?", value):
            matches += 1
            continue
        compact_format = "%Y%m" if len(value) == 6 else "%Y%m%d" if len(value) == 8 else None
        if compact_format and value.isdigit():
            try:
                datetime.strptime(value, compact_format)
            except ValueError:
                continue
            matches += 1
    return matches >= max(1, min(2, len(samples)))


def _is_rate_like(lower_name: str, semantic_type: str) -> bool:
    return semantic_type in {"rate", "ratio", "percentage"} or _contains_any(
        lower_name, ["rate", "ratio", "pct", "percent", "%", "率", "占比", "比例"]
    )


def _is_likely_business_dimension_name(lower_name: str) -> bool:
    return _contains_any(
        lower_name,
        [
            "region", "province", "city", "country", "area", "zone", "market",
            "channel", "source", "platform", "store", "shop", "brand", "product",
            "sku", "spu", "category", "type", "segment", "customer", "client",
            "status", "state", "stage", "level", "tier", "grade", "owner",
            "department", "dept", "team", "campaign", "activity", "scene",
            "地区", "省", "城市", "国家", "区域", "市场", "渠道", "来源",
            "平台", "门店", "店铺", "品牌", "商品", "产品", "品类", "类目",
            "类别", "类型", "客户", "用户", "客群", "分层", "等级", "状态",
            "阶段", "负责人", "部门", "团队", "活动", "场景",
        ],
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


# ── System prompt ─────────────────────────────────────────────────────────

_SEMANTIC_INFERENCE_SYSTEM_PROMPT = """You are a semantic analyst for user-uploaded Excel/CSV datasets.
Your job is to improve a draft semantic interpretation of columns. You only produce draft suggestions.
Humans are the final authority and must confirm or edit your output before it becomes a semantic layer.
Return strict JSON. Never invent columns. Never mark fields as confirmed.

Dimension discovery rules:
- Actively identify fields useful for grouping or filtering as dimensions.
- Prefer low-confidence dimensions with caveats over text for ambiguous categorical business fields.
- Keep true free-text fields as text.

Excel multi-sheet rules:
- The workbook may contain multiple sheets. Each sheet is a separate data table.
- Never mix columns from different sheets unless a relationship is explicit.
- Include sheet_name or source_table in every metric and dimension.
- If you cannot determine which sheet is the fact table, add a question_for_user.
"""


# ── Dataset profile builders (public API) ─────────────────────────────────

def build_semantic_dataset_profile(dataset) -> dict:
    """Build a structured dataset profile for semantic inference.

    For CSV: returns single-sheet profile.
    For Excel: returns multi-sheet profile with sheet_name per column.
    """
    import pandas as pd
    from pathlib import Path

    path = Path(dataset.path)
    is_excel = dataset.content_type and ("excel" in dataset.content_type.lower() or "xls" in dataset.content_type.lower())
    if not is_excel:
        is_excel = path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}

    if is_excel:
        return _profile_excel_workbook(path, dataset)

    try:
        df = pd.read_csv(path, nrows=500)
        columns = _profile_columns_for_semantic(df)
    except Exception:
        return {"error": "Failed to read CSV", "filename": dataset.filename, "dataset_id": dataset.id}

    return {
        "filename": dataset.filename,
        "dataset_id": dataset.id,
        "format": "csv",
        "sheets": [{
            "sheet_name": "Sheet1",
            "source_table": dataset.filename,
            "row_count": len(df),
            "columns": columns,
        }],
    }


def _profile_excel_workbook(path, dataset) -> dict:
    import pandas as pd

    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        return {"error": f"Failed to read Excel: {e}", "filename": dataset.filename, "dataset_id": dataset.id}

    sheets = []
    for sheet_name in xl.sheet_names:
        try:
            df = pd.read_excel(path, sheet_name=sheet_name, nrows=100)
            columns = _profile_columns_for_semantic(df)
            for c in columns:
                c["sheet_name"] = sheet_name
                c["source_table"] = f"{dataset.filename}#{sheet_name}"
            sheets.append({
                "sheet_name": sheet_name,
                "source_table": f"{dataset.filename}#{sheet_name}",
                "row_count": len(df),
                "columns": columns,
            })
        except Exception:
            sheets.append({
                "sheet_name": sheet_name,
                "source_table": f"{dataset.filename}#{sheet_name}",
                "row_count": 0,
                "columns": [],
                "error": "Could not read sheet",
            })

    return {
        "filename": dataset.filename,
        "dataset_id": dataset.id,
        "format": "excel",
        "sheet_count": len(xl.sheet_names),
        "sheet_names": xl.sheet_names,
        "sheets": sheets,
    }


def _profile_columns_for_semantic(df) -> list[dict]:
    import pandas as pd

    cols = []
    for col_name in df.columns:
        series = df[col_name]
        dtype = str(series.dtype)
        null_pct = round(series.isna().mean() * 100, 1)
        unique_count = int(series.nunique())
        samples = series.dropna().head(5).astype(str).tolist()
        col = {
            "name": str(col_name),
            "dtype": dtype,
            "null_pct": null_pct,
            "unique_count": unique_count,
            "sample_values": samples[:5],
        }
        try:
            if pd.api.types.is_numeric_dtype(series):
                col["min"] = float(series.min()) if pd.notna(series.min()) else None
                col["max"] = float(series.max()) if pd.notna(series.max()) else None
                col["mean"] = round(float(series.mean()), 2) if pd.notna(series.mean()) else None
        except Exception:
            pass
        cols.append(col)
    return cols
