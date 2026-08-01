"""Semantic layer helpers: metric cards, angle linking, conflict detection (extracted from artifact_manifest.py)."""
from typing import Any
from uuid import uuid4

from app.models.schemas import CardMetric, ManifestCard


def _build_metric_cards(
    semantic_layer: dict | None,
    all_tables: list[dict],
) -> tuple[list[ManifestCard], dict[str, list[dict[str, Any]]]]:
    """Build generic KPI cards from semantic metrics and available table rows.

    This intentionally avoids domain-specific labels such as revenue/orders/AOV.
    """
    metrics = (semantic_layer or {}).get("metrics") or []
    if not metrics:
        return [], {}

    card_row: dict[str, Any] = {}
    card_metrics: list[CardMetric] = []
    seen_fields: set[str] = set()

    for metric in metrics[:4]:
        if not isinstance(metric, dict):
            continue
        source_col = str(metric.get("source_column") or metric.get("name") or "")
        label = str(metric.get("name") or source_col)
        aggregation = str(metric.get("aggregation") or "sum").lower()
        if not source_col or source_col in seen_fields:
            continue

        values: list[float] = []
        for table in all_tables:
            rows = table.get("rows") or table.get("preview") or []
            if not isinstance(rows, list):
                continue
            if rows and source_col not in rows[0]:
                continue
            for row in rows:
                try:
                    value = row.get(source_col) if isinstance(row, dict) else None
                    if isinstance(value, (int, float)):
                        values.append(float(value))
                except Exception:
                    continue
            if values:
                break

        if not values:
            continue
        if aggregation in {"avg", "mean", "weighted_avg"}:
            value = sum(values) / len(values)
        elif aggregation in {"count", "count_distinct"}:
            value = len(set(values)) if aggregation == "count_distinct" else len(values)
        elif aggregation == "min":
            value = min(values)
        elif aggregation == "max":
            value = max(values)
        else:
            value = sum(values)

        field = f"metric_{len(card_metrics) + 1}"
        card_row[field] = round(value, 4)
        card_metrics.append(CardMetric(label=label, field=field, format=None, signed=None))
        seen_fields.add(source_col)

    if not card_metrics:
        return [], {}

    dataset_key = "ds_metric_cards"
    return [ManifestCard(id=f"card_{uuid4().hex[:8]}", dataset=dataset_key, metrics=card_metrics)], {dataset_key: [card_row]}


def link_angles_to_items(
    item_names: list[str],
    candidate_angles: list[Any] | None,
) -> dict[str, list[str]]:
    """Link items to candidate angles by keyword overlap.

    Returns dict mapping each item name to a list of angle IDs.
    """
    if not candidate_angles:
        return {}
    selected_angles = [a for a in candidate_angles if getattr(a, "selected", False)]
    if not selected_angles:
        return {}
    result: dict[str, list[str]] = {}
    for name in item_names:
        name_lower = name.lower()
        linked: list[str] = []
        for angle in selected_angles:
            angle_text = (
                (getattr(angle, "question", "") + " " +
                 " ".join(getattr(angle, "measures", [])) + " " +
                 " ".join(getattr(angle, "dimensions", [])))
                .lower()
            )
            angle_words = set(angle_text.split())
            name_words = set(name_lower.replace("_", " ").replace("-", " ").split())
            if angle_words & name_words:
                linked.append(getattr(angle, "id", ""))
        if linked:
            result[name] = linked
    return result


def detect_semantic_conflicts(
    semantic_layer: dict | None,
) -> tuple[list[dict], list[dict]]:
    """Detect conflicting and ambiguous metric/dimension definitions."""
    if not semantic_layer:
        return [], []
    metrics = semantic_layer.get("metrics", [])
    conflicts: list[dict] = []
    ambiguities: list[dict] = []
    seen: dict[str, list[dict]] = {}
    for m in metrics:
        name = m.get("name", "") if isinstance(m, dict) else getattr(m, "name", "")
        if not name:
            continue
        seen.setdefault(name, []).append(m if isinstance(m, dict) else m.model_dump(mode="json"))
    for name, entries in seen.items():
        if len(entries) > 1:
            aggs = {e.get("aggregation", "unknown") for e in entries}
            if len(aggs) > 1:
                conflicts.append({
                    "type": "duplicate_metric",
                    "metric": name,
                    "aggregations": list(aggs),
                    "detail": f"Metric '{name}' has conflicting aggregations: {', '.join(aggs)}",
                })
    return conflicts, ambiguities
