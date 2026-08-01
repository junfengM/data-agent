from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.tools.validation_types import ValidationResult


# ── Canonicalization helpers ───────────────────────────────────────────────

def normalize_metric_name(name: str) -> str:
    """Normalize a metric name for grouping and comparison.

    Rules:
      - lower-case
      - trim whitespace
      - collapse internal whitespace to single space
      - normalize Chinese parentheses （）→ ()
      - normalize en-dash / em-dash → hyphen
    """
    normalized = name.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("\u2018", "_").replace("\u2019", "_")
    normalized = normalized.replace("\uff08", "(").replace("\uff09", ")")
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\u3001", ",")
    return normalized


def normalize_formula(formula: str) -> str:
    """Normalize a formula string for safe comparison.

    Rules:
      - strip leading/trailing whitespace
      - collapse multiple spaces
      - normalize Chinese parentheses
      - lower-case
    Does NOT attempt semantic equivalence reasoning.
    """
    normalized = formula.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("\uff08", "(").replace("\uff09", ")")
    return normalized.lower()


def canonical_metric_key(metric: dict) -> str:
    """Create a canonical key for grouping metrics across different sources.

    Returns a string combining normalized name and source identity.
    This is stricter than name-only grouping used previously.
    """
    name = normalize_metric_name(str(metric.get("name", "")))
    source_table = str(metric.get("source_table", "")).strip()
    source_dataset = str(metric.get("source_dataset", "")).strip()

    if source_table:
        return f"{source_table}::{name}"
    if source_dataset:
        return f"{source_dataset}::{name}"
    return f"::{name}"


def extract_metric_signature(metric: dict) -> dict:
    """Extract a comparable signature from a metric dict."""
    return {
        "name": normalize_metric_name(str(metric.get("name", ""))),
        "formula": normalize_formula(str(metric.get("formula", ""))),
        "aggregation": str(metric.get("aggregation", "")).lower().strip(),
        "grain": str(metric.get("grain", "")).lower().strip(),
        "sources": sorted(_extract_sources(metric)),
        "source_table": str(metric.get("source_table", "")).strip(),
        "source_dataset": str(metric.get("source_dataset", "")).strip(),
    }


# ── SemanticAmbiguity (extended) ───────────────────────────────────────────

Severity = Literal["blocker", "warning", "info"]
RepairAction = Literal[
    "merge_duplicate",
    "rename_metric",
    "choose_primary",
    "split_by_grain",
    "split_by_source",
    "needs_user_confirmation",
]


@dataclass
class SemanticAmbiguity:
    metric_name: str
    conflict_type: str  # "duplicate_name", "conflicting_formula", etc.
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    severity: Severity = "warning"
    repair_action: RepairAction = "needs_user_confirmation"
    suggested_resolution: str = ""
    affected_metric_indices: list[int] = field(default_factory=list)


# ── Source extraction (upgraded) ───────────────────────────────────────────

def _extract_sources(metric: dict) -> list[str]:
    """Extract source identifiers from a metric dict.

    Uses sources list first, then falls back to source_column / source_dataset fields.
    Returns the first element of sources for canonical comparison (rule 5 compatibility).
    """
    sources = metric.get("sources", [])
    if sources:
        if isinstance(sources, list):
            return [str(s) for s in sources[:1]]
        return [str(sources)]

    result = []
    source_col = metric.get("source_column")
    source_ds = metric.get("source_dataset")
    if source_col:
        result.append(str(source_col))
    if source_ds:
        result.append(str(source_ds))
    return result


def _extract_all_sources(metric: dict) -> list[str]:
    """Extract ALL source identifiers for comprehensive comparison (precheck)."""
    result: list[str] = []
    sources = metric.get("sources", [])
    if sources:
        if isinstance(sources, list):
            result.extend(str(s) for s in sources)
        elif isinstance(sources, str):
            result.append(sources)
    source_col = metric.get("source_column")
    if source_col and str(source_col) not in result:
        result.append(str(source_col))
    source_ds = metric.get("source_dataset")
    if source_ds and str(source_ds) not in result:
        result.append(str(source_ds))
    source_table = metric.get("source_table")
    if source_table and str(source_table) not in result:
        result.append(str(source_table))
    return result


# ── Prefix stripping ───────────────────────────────────────────────────────

_PREFIXES = [
    "net_", "total_", "gross_", "avg_", "average_",
    "max_", "min_", "sum_", "count_",
]


def _strip_common_prefix(name: str) -> str:
    """Strip common metric name prefixes to detect near-duplicates."""
    lower = name.lower()
    for prefix in _PREFIXES:
        if lower.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return name


# ── Severity / repair logic ───────────────────────────────────────────────

def _classify_severity(
    conflict_type: str,
    name: str,
    metrics: list[dict],
    group: list[dict],
) -> tuple[Severity, RepairAction, str]:
    """Determine severity, repair action, and suggested resolution."""
    if conflict_type == "duplicate_name":
        sigs = [extract_metric_signature(m) for m in group]
        if len({(s["formula"], s["aggregation"]) for s in sigs}) == 1:
            return (
                "warning",
                "merge_duplicate",
                f"同名同公式的 '{name}' 可以合并为一条；检查是否来自不同数据源需保留分离。",
            )
        return (
            "warning",
            "choose_primary",
            f"'{name}' 出现多次；请确认哪一条是主定义，或为变体创建不同名称。",
        )

    if conflict_type == "conflicting_formula":
        return (
            "blocker",
            "rename_metric",
            f"'{name}' 有不同公式，必须重命名为不同指标名（如 revenue_orders / revenue_refunds）。",
        )

    if conflict_type == "conflicting_aggregation":
        return (
            "blocker",
            "rename_metric",
            f"'{name}' 聚合方式冲突；请按聚合方式拆分为不同指标（如 revenue_sum / revenue_avg）。",
        )

    if conflict_type == "conflicting_grain":
        return (
            "blocker",
            "split_by_grain",
            f"'{name}' 粒度不同；请按粒度拆分为不同指标（如 revenue_daily / revenue_monthly）。",
        )

    if conflict_type == "conflicting_source":
        return (
            "blocker",
            "split_by_source",
            f"'{name}' 来自不同数据源；请按来源拆分为不同指标或确认是否应合并。",
        )

    if conflict_type == "near_duplicate":
        names = list(group) if isinstance(group, set) else []
        return (
            "warning",
            "needs_user_confirmation",
            f"名称相近的指标 {sorted(names) if names else name} 可能指同一业务概念；请确认是否需要合并或显式区分。",
        )

    return ("warning", "needs_user_confirmation", "")


# ── Detection ──────────────────────────────────────────────────────────────

def detect_semantic_ambiguities(metrics: list[dict]) -> list[SemanticAmbiguity]:
    """Detect ambiguous or conflicting metrics in the semantic layer.

    Implements six detection rules using canonicalized names:
    1. duplicate_name        — identical metric names (by normalize_metric_name)
    2. conflicting_formula   — same name, different formula
    3. conflicting_aggregation — same name, conflicting aggregation
    4. conflicting_grain     — same name, different grain
    5. conflicting_source    — same name, different sources
    6. near_duplicate        — names differing only by prefix
    """
    ambiguities: list[SemanticAmbiguity] = []

    if not metrics:
        return ambiguities

    # ── Index metric positions ──
    index_map: dict[int, int] = {}
    for idx, m in enumerate(metrics):
        index_map[idx] = idx

    # ── Group metrics by normalized name for rules 1-5 ──
    by_name: dict[str, list[dict]] = {}
    by_name_indices: dict[str, list[int]] = {}
    for idx, m in enumerate(metrics):
        name = normalize_metric_name(str(m.get("name", "")))
        if name not in by_name:
            by_name[name] = []
            by_name_indices[name] = []
        by_name[name].append(m)
        by_name_indices[name].append(idx)

    for name, group in by_name.items():
        if len(group) < 2:
            continue
        indices = by_name_indices.get(name, [])

        # 1. duplicate_name
        severity, repair, resolution = _classify_severity("duplicate_name", name, metrics, group)
        ambiguities.append(SemanticAmbiguity(
            metric_name=name,
            conflict_type="duplicate_name",
            description=f"Metric '{name}' appears {len(group)} times",
            details={
                "count": len(group),
                "indices": indices,
            },
            severity=severity,
            repair_action=repair,
            suggested_resolution=resolution,
            affected_metric_indices=indices,
        ))

        # 2. conflicting_formula
        formulas = {normalize_formula(str(m.get("formula", ""))) for m in group if m.get("formula") is not None}
        if len(formulas) > 1:
            severity, repair, resolution = _classify_severity("conflicting_formula", name, metrics, group)
            ambiguities.append(SemanticAmbiguity(
                metric_name=name,
                conflict_type="conflicting_formula",
                description=f"Metric '{name}' has {len(formulas)} different formulas",
                details={"formulas": sorted(formulas)},
                severity=severity,
                repair_action=repair,
                suggested_resolution=resolution,
                affected_metric_indices=indices,
            ))

        # 3. conflicting_aggregation
        agg_present = [m for m in group if "aggregation" in m]
        agg_absent = [m for m in group if "aggregation" not in m]
        agg_values = {str(m["aggregation"]).lower().strip() for m in agg_present}
        if (len(agg_present) >= 2 and len(agg_values) > 1) or (len(agg_present) >= 1 and len(agg_absent) >= 1):
            effective_aggs = sorted(agg_values | {"sum"})
            severity, repair, resolution = _classify_severity("conflicting_aggregation", name, metrics, group)
            ambiguities.append(SemanticAmbiguity(
                metric_name=name,
                conflict_type="conflicting_aggregation",
                description=f"Metric '{name}' has conflicting aggregations: {effective_aggs}",
                details={"aggregations": effective_aggs},
                severity=severity,
                repair_action=repair,
                suggested_resolution=resolution,
                affected_metric_indices=indices,
            ))

        # 4. conflicting_grain
        grains = {str(m.get("grain", "")).lower().strip() for m in group if m.get("grain") is not None}
        if len(grains) > 1:
            severity, repair, resolution = _classify_severity("conflicting_grain", name, metrics, group)
            ambiguities.append(SemanticAmbiguity(
                metric_name=name,
                conflict_type="conflicting_grain",
                description=f"Metric '{name}' has conflicting grains: {sorted(grains)}",
                details={"grains": sorted(grains)},
                severity=severity,
                repair_action=repair,
                suggested_resolution=resolution,
                affected_metric_indices=indices,
            ))

        # 5. conflicting_source
        source_sets: list[frozenset[str]] = []
        for m in group:
            src = _extract_all_sources(m)
            source_sets.append(frozenset(src))
        if len(set(source_sets)) > 1:
            severity, repair, resolution = _classify_severity("conflicting_source", name, metrics, group)
            ambiguities.append(SemanticAmbiguity(
                metric_name=name,
                conflict_type="conflicting_source",
                description=f"Metric '{name}' has conflicting source references",
                details={"sources": sorted(str(sorted(s)) for s in set(source_sets))},
                severity=severity,
                repair_action=repair,
                suggested_resolution=resolution,
                affected_metric_indices=indices,
            ))

    # ── Rule 6: near_duplicate names ──
    stripped_map: dict[str, set[str]] = {}
    stripped_indices: dict[str, list[int]] = {}
    for idx, m in enumerate(metrics):
        original = normalize_metric_name(str(m.get("name", "")))
        stripped = normalize_metric_name(_strip_common_prefix(original))
        if stripped not in stripped_map:
            stripped_map[stripped] = set()
            stripped_indices[stripped] = []
        stripped_map[stripped].add(original)
        stripped_indices[stripped].append(idx)

    for stripped, names in stripped_map.items():
        if len(names) > 1:
            name_list = sorted(names)
            idx_list = stripped_indices.get(stripped, [])
            severity, repair, resolution = _classify_severity("near_duplicate", stripped, metrics, set(name_list))
            ambiguities.append(SemanticAmbiguity(
                metric_name=stripped,
                conflict_type="near_duplicate",
                description=f"Near-duplicate metric names detected: {', '.join(name_list)}",
                details={"names": name_list, "base_name": stripped},
                severity=severity,
                repair_action=repair,
                suggested_resolution=resolution,
                affected_metric_indices=idx_list,
            ))

    return ambiguities


# ── Validation gate ────────────────────────────────────────────────────────

def validate_semantic_ambiguity(semantic_layer_data: dict | None) -> ValidationResult:
    """Validation gate: detect ambiguous or conflicting metric definitions.

    Now includes fix_hint, owner_layer, and detailed repair guidance per ambiguity.
    Blockers cause gate failure; warnings are non-blocking.
    """
    if not semantic_layer_data or not semantic_layer_data.get("metrics"):
        return ValidationResult(
            gate_id="semantic_ambiguity",
            passed=True,
            severity="warning",
            message="No semantic layer metrics to validate",
        )

    metrics = semantic_layer_data["metrics"]
    ambiguities = detect_semantic_ambiguities(metrics)

    if not ambiguities:
        return ValidationResult(
            gate_id="semantic_ambiguity",
            passed=True,
            severity="pass",
            message="No semantic ambiguities detected",
            details={"metrics_checked": len(metrics), "ambiguities": 0},
        )

    blockers = [a for a in ambiguities if a.severity == "blocker"]
    warnings = [a for a in ambiguities if a.severity == "warning"]
    infos = [a for a in ambiguities if a.severity == "info"]

    fix_hints: list[str] = []
    for a in blockers:
        fix_hints.append(f"[{a.severity}] {a.conflict_type}: {a.metric_name} — {a.suggested_resolution}")
    for a in warnings:
        fix_hints.append(f"[{a.severity}] {a.conflict_type}: {a.metric_name} — {a.suggested_resolution}")

    return ValidationResult(
        gate_id="semantic_ambiguity",
        passed=len(blockers) == 0,
        severity="fail" if blockers else ("warning" if warnings else "info"),
        message=f"{len(ambiguities)} semantic ambiguities detected ({len(blockers)} blockers, {len(warnings)} warnings, {len(infos)} info)",
        details={
            "metrics_checked": len(metrics),
            "ambiguities": len(ambiguities),
            "blockers": len(blockers),
            "warnings": len(warnings),
            "infos": len(infos),
            "ambiguity_details": [
                {
                    "name": a.metric_name,
                    "type": a.conflict_type,
                    "description": a.description,
                    "severity": a.severity,
                    "repair_action": a.repair_action,
                    "suggested_resolution": a.suggested_resolution,
                    "affected_metric_indices": a.affected_metric_indices,
                }
                for a in ambiguities
            ],
        },
        fix_hint="; ".join(fix_hints) if fix_hints else None,
        owner_layer="semantic_layer",
    )


# ── Merge precheck (for confirm flow) ──────────────────────────────────────

@dataclass
class SemanticMergePreview:
    """Preview of what would happen when merging a draft into the active layer."""
    can_confirm: bool
    blockers: list[SemanticAmbiguity] = field(default_factory=list)
    warnings: list[SemanticAmbiguity] = field(default_factory=list)
    incoming_metrics: list[str] = field(default_factory=list)
    would_replace: list[str] = field(default_factory=list)
    would_add: list[str] = field(default_factory=list)
    would_keep: list[str] = field(default_factory=list)
    requires_user_confirmation: bool = False


def precheck_semantic_layer_merge(
    existing_layer: dict | None,
    incoming_payload: dict,
) -> SemanticMergePreview:
    """Check for conflicts before confirming a semantic draft into the active layer.

    Returns a preview that identifies blockers (must fix before confirm),
    warnings (can proceed but should review), and what metrics would be
    added vs replaced.
    """
    existing_metrics: list[dict] = []
    if existing_layer and isinstance(existing_layer, dict):
        existing_metrics = existing_layer.get("metrics", []) or []

    incoming_metrics: list[dict] = incoming_payload.get("metrics", []) or []

    # ── Build canonical lookup for existing metrics ──
    existing_keys: dict[str, dict] = {}
    for m in existing_metrics:
        key = canonical_metric_key(m)
        existing_keys[key] = m

    # ── Classify incoming metrics ──
    would_replace: list[str] = []
    would_add: list[str] = []
    would_keep: list[str] = []

    for m in incoming_metrics:
        key = canonical_metric_key(m)
        name = str(m.get("name", ""))
        if key in existing_keys:
            existing = existing_keys[key]
            existing_sig = extract_metric_signature(existing)
            incoming_sig = extract_metric_signature(m)
            if existing_sig == incoming_sig:
                would_keep.append(name)
            else:
                would_replace.append(name)
        else:
            would_add.append(name)

    # ── Detect ambiguities across the merged set (existing + incoming) ──
    merged_metrics = existing_metrics + incoming_metrics
    all_ambiguities = detect_semantic_ambiguities(merged_metrics)

    blockers = [a for a in all_ambiguities if a.severity == "blocker"]
    warning_ambiguities = [a for a in all_ambiguities if a.severity == "warning"]

    # ── Additional precheck: cross-source name conflicts ──
    incoming_names = {normalize_metric_name(str(m.get("name", ""))) for m in incoming_metrics}
    for m in existing_metrics:
        existing_name = normalize_metric_name(str(m.get("name", "")))
        if existing_name in incoming_names:
            existing_sources = set(_extract_all_sources(m))
            for im in incoming_metrics:
                if normalize_metric_name(str(im.get("name", ""))) == existing_name:
                    incoming_sources = set(_extract_all_sources(im))
                    if existing_sources != incoming_sources and existing_sources and incoming_sources:
                        if not any(
                            a.metric_name == existing_name and a.conflict_type == "conflicting_source"
                            for a in all_ambiguities
                        ):
                            warning_ambiguities.append(SemanticAmbiguity(
                                metric_name=existing_name,
                                conflict_type="conflicting_source",
                                description=f"'{existing_name}' exists in both existing layer and incoming draft with different sources",
                                details={"existing_sources": sorted(existing_sources), "incoming_sources": sorted(incoming_sources)},
                                severity="warning",
                                repair_action="needs_user_confirmation",
                                suggested_resolution=f"确认 '{existing_name}' 从不同数据源合并是否合理，或需拆分为不同指标名。",
                            ))
                    break

    return SemanticMergePreview(
        can_confirm=len(blockers) == 0,
        blockers=blockers,
        warnings=warning_ambiguities,
        incoming_metrics=[str(m.get("name", "")) for m in incoming_metrics],
        would_replace=would_replace,
        would_add=would_add,
        would_keep=would_keep,
        requires_user_confirmation=len(warning_ambiguities) > 0 or len(blockers) > 0,
    )
