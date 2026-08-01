from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SemanticLayer:
    metrics: list[dict[str, Any]] = field(default_factory=list)
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    joins: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    source_precedence: dict[str, Any] = field(default_factory=dict)
    validation_rules: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceCategoryConfig:
    id: str
    label: str
    placeholder: str
    description: str = ""
    helper_skills: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectPreflight:
    project_id: str
    project_name: str
    project_contexts: list[dict[str, Any]]
    semantic_layer: SemanticLayer
    dataset_profiles: list[dict[str, Any]]
    context_gaps: list[str]
    validation_obligations: list[str]
    source_routing: dict[str, str] = field(default_factory=dict)
    onboarding_progress: dict[str, Any] = field(default_factory=dict)
    source_category_config: list[SourceCategoryConfig] = field(default_factory=list)
    final_obligations: list[str] = field(default_factory=list)
    hero_prompt_candidates: list[dict[str, str]] = field(default_factory=list)
    active_semantic_layer_meta: dict[str, Any] | None = None


CONTEXT_BODY_LIMIT = 1200
CONTEXT_BODY_LIMITS = {
    "metric_definition": 6000,
    "business_context": 4000,
    "data_quality_note": 4000,
}
SEMANTIC_LAYER_MAX_BYTES = 2 * 1024 * 1024
YAML_SUFFIXES = {".yaml", ".yml"}


def _bounded_text(value: str, limit: int = CONTEXT_BODY_LIMIT) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _safe_yaml_file(path: Path, *, max_bytes: int = SEMANTIC_LAYER_MAX_BYTES) -> bool:
    try:
        if path.suffix.lower() not in YAML_SUFFIXES:
            return False
        if path.is_symlink() or not path.is_file():
            return False
        if path.stat().st_size > max_bytes:
            return False
    except OSError:
        return False
    return True


def load_semantic_layer(semantic_layer_path: Path | None) -> SemanticLayer:
    if semantic_layer_path is None or not semantic_layer_path.exists():
        return SemanticLayer()
    if not _safe_yaml_file(semantic_layer_path):
        return SemanticLayer()

    try:
        with open(semantic_layer_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return SemanticLayer()
        return SemanticLayer(
            metrics=data.get("metrics", []),
            dimensions=data.get("dimensions", []),
            sources=data.get("sources", []),
            filters=data.get("filters", []),
            joins=data.get("joins", []),
            caveats=data.get("caveats", []),
            patterns=data.get("patterns", []),
            source_precedence=data.get("source_precedence", {}),
            validation_rules=data.get("validation", {}),
        )
    except Exception:
        return SemanticLayer()


def load_source_category_config(config_path: Path | None) -> list[SourceCategoryConfig]:
    if config_path is None or not config_path.exists():
        return []
    if not _safe_yaml_file(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        categories = data.get("categories", []) if isinstance(data, dict) else []
        return [
            SourceCategoryConfig(
                id=cat["id"],
                label=cat.get("label", cat["id"]),
                placeholder=cat.get("placeholder", f"~~{cat['id']}"),
                description=cat.get("description", ""),
                helper_skills=cat.get("helper_skills", []),
                examples=cat.get("examples", []),
            )
            for cat in categories
            if isinstance(cat, dict) and cat.get("id")
        ]
    except Exception:
        return []


def derive_semantic_layer(profiles: list[Any]) -> SemanticLayer:
    """Auto-generate a lightweight temporary semantic layer from dataset profiles."""
    metrics: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    caveats: list[dict[str, Any]] = []
    date_keywords = ["date", "time", "day", "month", "year", "日期", "时间", "年", "月", "日"]

    for profile in profiles:
        filename = getattr(profile, "filename", "unknown")
        row_count = getattr(profile, "row_count", 0)
        sources.append({
            "name": filename,
            "path": getattr(profile, "dataset_id", ""),
            "row_count": row_count,
        })
        for column in getattr(profile, "columns", []):
            name = getattr(column, "name", "")
            dtype = getattr(column, "dtype", "")
            lower = name.lower()
            unique_count = getattr(column, "unique_count", 0)
            non_null = getattr(column, "non_null_count", 0)
            null_pct = getattr(column, "null_pct", 0.0)
            base = {
                "name": name,
                "source": filename,
                "dtype": dtype,
                "non_null_count": non_null,
                "null_pct": null_pct,
            }
            # Check date keywords BEFORE numeric types — columns like "date" (int64)
            # are more likely temporal dimensions than numeric metrics.
            if any(keyword in lower for keyword in date_keywords):
                dimensions.append({
                    **base,
                    "type": "date/time",
                    "grain": "inferred from values",
                    "caveats": ["Auto-inferred temporal dimension."],
                })
            elif "int" in dtype or "float" in dtype or "decimal" in dtype:
                entry = {
                    **base,
                    "aggregation": "unknown",
                    "grain": "dataset row",
                    "caveats": ["Auto-inferred numeric metric; confirm definition before decision use."],
                }
                if null_pct > 20:
                    entry["caveats"].append(
                        f"Column '{name}' has {null_pct:.0f}% null values; completeness is low."
                    )
                    caveats.append({"column": name, "null_pct": null_pct, "message": entry["caveats"][-1]})
                metrics.append(entry)
            elif unique_count and unique_count <= max(50, row_count * 0.2 if row_count else 50):
                dimensions.append({
                    **base,
                    "type": "categorical",
                    "unique_count": unique_count,
                    "caveats": ["Auto-inferred categorical dimension."],
                })

    if not metrics:
        caveats.append({"message": "No numeric metrics were auto-detected; analysis may rely on counts or categorical summaries."})
    return SemanticLayer(metrics=metrics[:20], dimensions=dimensions[:30], sources=sources, caveats=caveats)


def select_active_layer(layers: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not layers:
        return None
    active = next((layer for layer in layers if layer.get("is_active")), None)
    if active:
        return active
    # Sort by created_at descending when no explicit is_active flag
    return sorted(layers, key=lambda l: l.get("created_at", ""), reverse=True)[0]


def build_preflight_envelope(
    *,
    project: Any | None,
    project_contexts: list[Any],
    semantic_layer: SemanticLayer,
    profiles: list[Any],
    source_routing: dict[str, str] | None = None,
    onboarding_progress: dict[str, Any] | None = None,
    source_category_config: list[SourceCategoryConfig] | None = None,
    project_layers: list[dict[str, Any]] | None = None,
) -> ProjectPreflight:
    project_id = getattr(project, "id", "") if project else ""
    project_name = getattr(project, "name", "No project") if project else "No project"
    context_payload: list[dict[str, Any]] = []
    for ctx in project_contexts:
        kind = getattr(ctx, "kind", None) or getattr(ctx, "type", "context")
        context_payload.append({
            "type": kind,
            "title": getattr(ctx, "title", ""),
            "body": _bounded_text(
                getattr(ctx, "body", ""),
                limit=CONTEXT_BODY_LIMITS.get(kind, CONTEXT_BODY_LIMIT),
            ),
        })
    profile_payload = [profile.model_dump() if hasattr(profile, "model_dump") else profile for profile in profiles]
    gaps: list[str] = []
    if not project:
        gaps.append("No project selected; business context is limited.")
    if not project_contexts:
        gaps.append("No project context notes are available.")
    if not semantic_layer.metrics and not semantic_layer.dimensions:
        gaps.append("No semantic layer metrics or dimensions are configured; using dataset-profile inference only.")
    if not profiles:
        gaps.append("No datasets selected for this run.")

    obligations = [
        "Cite which dataset columns support each quantitative claim.",
        "Surface missing context and data-quality caveats before recommendations.",
        "Do not present inferred metrics as canonical definitions unless they appear in the semantic layer.",
        "Return candidate analysis angles and explain why selected angles were prioritized.",
    ]
    final_obligations = [
        "Before final answer, verify all chart/table ids referenced in narrative exist in the manifest.",
        "Include validation gate status and any unresolved warnings in the run log.",
    ]
    hero_prompt_candidates = [
        {"label": "Executive summary", "prompt": "Summarize the top KPI movements and caveats."},
        {"label": "Find anomalies", "prompt": "Identify unusual changes, segments, or outliers in the selected data."},
        {"label": "Explain drivers", "prompt": "Rank likely drivers using available dimensions and note missing evidence."},
    ]

    active_layer = select_active_layer(project_layers or [])
    active_layer_meta = None
    if active_layer:
        active_layer_meta = {
            "id": active_layer.get("id"),
            "name": active_layer.get("name"),
            "path": active_layer.get("path"),
            "is_active": active_layer.get("is_active", False),
        }

    return ProjectPreflight(
        project_id=project_id,
        project_name=project_name,
        project_contexts=context_payload,
        semantic_layer=semantic_layer,
        dataset_profiles=profile_payload,
        context_gaps=gaps,
        validation_obligations=obligations,
        source_routing=source_routing or {},
        onboarding_progress=onboarding_progress or {},
        source_category_config=source_category_config or [],
        final_obligations=final_obligations,
        hero_prompt_candidates=hero_prompt_candidates,
        active_semantic_layer_meta=active_layer_meta,
    )


def preflight_to_markdown(preflight: ProjectPreflight) -> str:
    lines: list[str] = []
    lines.append(f"# Project Preflight: {preflight.project_name}")
    if preflight.project_id:
        lines.append(f"Project ID: {preflight.project_id}")
    if preflight.active_semantic_layer_meta:
        lines.append(
            "Active semantic layer: "
            f"{preflight.active_semantic_layer_meta.get('name') or preflight.active_semantic_layer_meta.get('id')}"
        )
    if preflight.context_gaps:
        lines.append("\n## Context Gaps")
        for gap in preflight.context_gaps:
            lines.append(f"- {gap}")
    if preflight.project_contexts:
        lines.append("\n## Project Context")
        for ctx in preflight.project_contexts:
            lines.append(f"- **{ctx['title']}** ({ctx['type']}): {ctx['body']}")
    if preflight.semantic_layer.metrics or preflight.semantic_layer.dimensions:
        lines.append("\n## Semantic Layer")
        if preflight.semantic_layer.metrics:
            lines.append("Metrics:")
            for metric in preflight.semantic_layer.metrics:
                details = [
                    f"formula={metric.get('formula') or metric.get('description') or 'unknown'}",
                    f"aggregation={metric.get('aggregation') or 'unknown'}",
                    f"grain={metric.get('grain') or 'unknown'}",
                ]
                if metric.get("source_column"):
                    details.append(f"source_column={metric['source_column']}")
                caveats = metric.get("caveats") or metric.get("caveat") or []
                if isinstance(caveats, str):
                    caveats = [caveats]
                if caveats:
                    details.append(f"caveats={'; '.join(str(item) for item in caveats)}")
                lines.append(f"- {metric.get('name')}: {', '.join(details)}")
        if preflight.semantic_layer.dimensions:
            lines.append("Dimensions:")
            for dim in preflight.semantic_layer.dimensions:
                lines.append(
                    f"- {dim.get('name')}: type={dim.get('type') or 'unknown'}, "
                    f"source_column={dim.get('source_column') or dim.get('name')}"
                )
    if preflight.source_routing:
        lines.append("\n## Source Routing Preferences")
        for category, preference in preflight.source_routing.items():
            lines.append(f"- {category}: {preference}")
    if preflight.source_category_config:
        lines.append("\n## Source Categories")
        for category in preflight.source_category_config:
            helper = f"; helpers: {', '.join(category.helper_skills)}" if category.helper_skills else ""
            lines.append(f"- {category.id} ({category.label}): {category.description}{helper}")
    if preflight.dataset_profiles:
        lines.append("\n## Complete Dataset Map")
        for profile in preflight.dataset_profiles:
            lines.append(
                f"### {profile.get('filename')}\n"
                f"- dataset_id={profile.get('dataset_id')}\n"
                f"- rows={profile.get('row_count')}; columns={profile.get('column_count')}"
            )
            for col in profile.get("columns", []):
                sample = ", ".join(str(item) for item in col.get("sample_values", [])[:5])
                lines.append(
                    f"- column={col.get('name')}; dtype={col.get('dtype')}; "
                    f"null_pct={col.get('null_pct')}; unique={col.get('unique_count')}; "
                    f"min={col.get('min_value')}; max={col.get('max_value')}; "
                    f"samples=[{sample}]"
                )
    lines.extend([
        "\n## Python Execution Contract",
        "- `dataset_paths` is an injected Python list of real file paths, not a directory.",
        "- Load the first CSV with `df = pd.read_csv(dataset_paths[0])`.",
        "- Never construct paths such as `dataset_paths/filename.csv`.",
        "- The process working directory is the current run artifact directory.",
        "- Save evidence using a relative filename such as `monthly_sales.csv` or `sales_trend.png`.",
        "- Do not write evidence files to /tmp; files outside the run directory are not collected.",
        "- Prefer vectorized groupby/pivot operations. Never loop over every source row and repeatedly filter the full dataframe.",
    ])
    lines.append("\n## Validation Obligations")
    for obligation in preflight.validation_obligations:
        lines.append(f"- {obligation}")
    if preflight.final_obligations:
        lines.append("\n## Finalization Obligations")
        for obligation in preflight.final_obligations:
            lines.append(f"- {obligation}")
    return "\n".join(lines)
