"""Deterministic evidence-integration checks for report_md evaluation.

These helpers are shared between the pre-final feedback gate
(feedback.py) and the post-run validation audit (validation.py).
"""
from __future__ import annotations

import re
from typing import Any


def normalize_evidence_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\s+", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return text


def _string_values(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            result.extend(_string_values(*value))
        elif isinstance(value, dict):
            result.extend(_string_values(*value.values()))
        else:
            text = str(value).strip()
            if text:
                result.append(text)
    return result


def _chart_reference_candidates(chart: dict[str, Any], chart_specs: list[dict[str, Any]]) -> set[str]:
    candidates: set[str] = set()
    for key in ("name", "title", "path", "asset_name"):
        value = chart.get(key)
        if value:
            candidates.add(str(value))
    data = chart.get("data") if isinstance(chart.get("data"), dict) else {}
    for key in ("path", "asset_name", "title", "name"):
        value = data.get(key)
        if value:
            candidates.add(str(value))
    chart_name = str(chart.get("name") or chart.get("title") or "")
    for spec in chart_specs or []:
        spec_name = str(spec.get("name") or "")
        spec_title = str(spec.get("title") or "")
        if chart_name and chart_name in {spec_name, spec_title}:
            candidates.update(_string_values(spec_name, spec_title))
    return {c for c in candidates if c}


def _is_file_chart(chart: dict[str, Any]) -> bool:
    data = chart.get("data") if isinstance(chart.get("data"), dict) else {}
    values = _string_values(
        chart.get("path"), chart.get("asset_name"),
        data.get("path"), data.get("asset_name"),
    )
    return any(v.lower().endswith((".html", ".png", ".jpg", ".jpeg", ".svg")) for v in values)


def chart_is_integrated(report_md: str, chart: dict[str, Any], chart_specs: list[dict[str, Any]]) -> bool:
    normalized_report = normalize_evidence_text(report_md)
    candidates = _chart_reference_candidates(chart, chart_specs)
    if not candidates:
        return False
    if _is_file_chart(chart):
        file_candidates = [c for c in candidates if c.lower().endswith((".html", ".png", ".jpg", ".jpeg", ".svg"))]
        return any(normalize_evidence_text(c) in normalized_report for c in file_candidates)
    return any(normalize_evidence_text(c) in normalized_report for c in candidates)


def _table_reference_candidates(table: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key in ("name", "title", "path", "source"):
        value = table.get(key)
        if value:
            candidates.add(str(value))
    data = table.get("data") if isinstance(table.get("data"), dict) else {}
    for key in ("name", "title", "path", "source"):
        value = data.get(key)
        if value:
            candidates.add(str(value))
    return {c for c in candidates if c}


def _table_columns(table: dict[str, Any]) -> list[str]:
    raw_columns = table.get("columns")
    if raw_columns is None and isinstance(table.get("data"), dict):
        raw_columns = table["data"].get("columns")
    columns: list[str] = []
    for col in raw_columns or []:
        if isinstance(col, dict):
            value = col.get("key") or col.get("label") or col.get("name")
        else:
            value = col
        if value:
            columns.append(str(value))
    return columns


def _table_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = table.get("rows")
    if rows is None and isinstance(table.get("data"), dict):
        rows = table["data"].get("rows")
    if not isinstance(rows, list):
        rows = table.get("preview")
    if rows is None and isinstance(table.get("data"), dict):
        rows = table["data"].get("preview")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _important_table_values(table: dict[str, Any], limit: int = 8) -> list[str]:
    values: list[str] = []
    rows = _table_rows(table)
    for row in rows[:5]:
        for value in row.values():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            if len(text) >= 2:
                values.append(text)
            if len(values) >= limit:
                return values
    return values


def table_is_integrated(report_md: str, table: dict[str, Any]) -> bool:
    normalized_report = normalize_evidence_text(report_md)
    for candidate in _table_reference_candidates(table):
        if normalize_evidence_text(candidate) in normalized_report:
            return True
    columns = _table_columns(table)
    column_hits = sum(1 for col in columns if normalize_evidence_text(col) in normalized_report)
    values = _important_table_values(table)
    value_hits = sum(1 for value in values if normalize_evidence_text(value) in normalized_report)
    if len(columns) <= 1:
        return value_hits >= 2
    return column_hits >= 2 or (column_hits >= 1 and value_hits >= 2)


def collect_execution_evidence(execution_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    for result in execution_results or []:
        tables.extend([t for t in result.get("tables", []) or [] if isinstance(t, dict)])
        charts.extend([c for c in result.get("charts", []) or [] if isinstance(c, dict)])
    return tables, charts


def infer_evidence_role(evidence: dict[str, Any]) -> str:
    name = str(evidence.get("name") or evidence.get("title") or "").lower()
    if "intermediate" in name:
        return "intermediate"
    if any(k in name for k in [
        "debug", "raw", "temp", "profile",
    ]):
        return "debug"
    if any(k in name for k in [
        "final", "summary", "monthly", "trend", "comparison",
        "ranking", "top", "core", "metrics", "strategy",
    ]):
        return "primary"
    if evidence.get("type") == "chart":
        return "primary"
    return "supporting"


def _evidence_identity_candidates(evidence: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key in ("name", "title"):
        value = evidence.get(key)
        if value:
            candidates.add(str(value))
    return {c for c in candidates if c}


def _manifest_ids_for_evidence(
    evidence: dict[str, Any],
    manifest_tables: list[dict] | None = None,
    manifest_charts: list[dict] | None = None,
) -> set[str]:
    names = _evidence_identity_candidates(evidence)
    normalized_names = {normalize_evidence_text(x) for x in names}
    ids: set[str] = set()
    for table in manifest_tables or []:
        title = normalize_evidence_text(str(table.get("title") or ""))
        if title and title in normalized_names:
            tid = table.get("id")
            if tid:
                ids.add(str(tid))
    for chart in manifest_charts or []:
        title = normalize_evidence_text(str(chart.get("title") or ""))
        asset_path = normalize_evidence_text(str(chart.get("asset_path") or ""))
        if (title and title in normalized_names) or (asset_path and asset_path in normalized_names):
            cid = chart.get("id")
            if cid:
                ids.add(str(cid))
    return {x for x in ids if x}


def evidence_is_bound_in_blocks(
    evidence: dict[str, Any],
    blocks: list[dict] | None,
    *,
    manifest_tables: list[dict] | None = None,
    manifest_charts: list[dict] | None = None,
) -> bool:
    if not blocks:
        return False
    evidence_names = _evidence_identity_candidates(evidence)
    evidence_names |= _manifest_ids_for_evidence(
        evidence,
        manifest_tables=manifest_tables,
        manifest_charts=manifest_charts,
    )
    for block in blocks:
        evidence_ids = set(str(x) for x in block.get("evidence_ids") or [])
        chart_id = block.get("chart_id")
        table_id = block.get("table_id")
        source_id = block.get("source_id")
        block_refs = set(evidence_ids)
        if chart_id:
            block_refs.add(str(chart_id))
        if table_id:
            block_refs.add(str(table_id))
        if source_id:
            block_refs.add(str(source_id))
        normalized_refs = {normalize_evidence_text(x) for x in block_refs}
        normalized_names = {normalize_evidence_text(x) for x in evidence_names}
        if normalized_refs & normalized_names:
            return True
    return False


_HIDDEN_ANCHOR_RE = re.compile(
    r"<!--\s*evidence\s*:\s*(.+?)\s*-->",
    re.IGNORECASE,
)


def _scan_hidden_evidence_anchors(report_md: str) -> set[str]:
    anchors: set[str] = set()
    for match in _HIDDEN_ANCHOR_RE.finditer(report_md):
        payload = match.group(1)
        for part in re.split(r"[;,]", payload):
            part = part.strip()
            eq = part.find("=")
            if eq > 0:
                values = part[eq + 1:].strip()
                for value in re.split(r"\s+", values):
                    value = value.strip()
                    if value:
                        anchors.add(normalize_evidence_text(value))
            else:
                for value in re.split(r"\s+", part):
                    value = value.strip()
                    if value:
                        anchors.add(normalize_evidence_text(value))
    return anchors


def evidence_is_integrated_in_report_md(
    report_md: str,
    evidence: dict[str, Any],
    chart_specs: list[dict[str, Any]] | None = None,
    blocks: list[dict] | None = None,
) -> bool:
    normalized_report = normalize_evidence_text(report_md)
    chart_specs = chart_specs or []
    evidence_type = evidence.get("type")

    if evidence_type == "chart":
        return chart_is_integrated(report_md, evidence, chart_specs)
    return table_is_integrated(report_md, evidence)


def _check_evidence_integration(
    report_md: str,
    evidence: dict[str, Any],
    chart_specs: list[dict[str, Any]] | None,
    blocks: list[dict] | None,
    *,
    manifest_tables: list[dict] | None = None,
    manifest_charts: list[dict] | None = None,
) -> bool:
    if evidence_is_bound_in_blocks(
        evidence, blocks,
        manifest_tables=manifest_tables,
        manifest_charts=manifest_charts,
    ):
        return True
    hidden_anchors = _scan_hidden_evidence_anchors(report_md)
    evidence_names = _evidence_identity_candidates(evidence)
    normalized_names = {normalize_evidence_text(n) for n in evidence_names}
    if normalized_names & hidden_anchors:
        return True
    return evidence_is_integrated_in_report_md(report_md, evidence, chart_specs, blocks)


def missing_report_evidence_integrations(
    *,
    report_md: str,
    execution_results: list[dict[str, Any]],
    chart_specs: list[dict[str, Any]] | None = None,
    blocks: list[dict] | None = None,
    manifest_tables: list[dict] | None = None,
    manifest_charts: list[dict] | None = None,
) -> list[dict[str, Any]]:
    tables, charts = collect_execution_evidence(execution_results)
    chart_specs = chart_specs or []
    missing: list[dict[str, Any]] = []
    for chart in charts:
        role = infer_evidence_role(chart)
        if role in ("debug", "intermediate"):
            continue
        if not _check_evidence_integration(
            report_md, chart, chart_specs, blocks,
            manifest_tables=manifest_tables,
            manifest_charts=manifest_charts,
        ):
            missing.append({
                "type": "chart",
                "name": chart.get("name") or chart.get("title"),
                "path": chart.get("path") or chart.get("asset_name"),
                "role": role,
                "reason": (
                    "file chart not linked in report_md"
                    if _is_file_chart(chart)
                    else "chart title/name not referenced in report_md"
                ),
            })
    for table in tables:
        role = infer_evidence_role(table)
        if role in ("debug", "intermediate"):
            continue
        if not _check_evidence_integration(
            report_md, table, chart_specs, blocks,
            manifest_tables=manifest_tables,
            manifest_charts=manifest_charts,
        ):
            missing.append({
                "type": "table",
                "name": table.get("name") or table.get("title"),
                "columns": _table_columns(table)[:8],
                "role": role,
                "reason": "table not referenced or materially represented in report_md",
            })
    return missing
