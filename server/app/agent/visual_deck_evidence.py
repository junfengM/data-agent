"""Evidence and source attachment helpers (extracted from visual_deck_blocks.py)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.visual_deck_constants import VISUAL_BLOCK_TYPES, _enum_value


def attach_stable_source_ids(manifest: Any, snapshot: Any) -> None:
    """Bind charts/tables back to manifest sources using filename hints."""
    sources = list(getattr(manifest, "sources", []) or [])
    if not sources:
        return

    source_ids = {str(getattr(source, "id", "")) for source in sources if getattr(source, "id", None)}
    source_by_hint: dict[str, str] = {}
    for source in sources:
        source_id = str(getattr(source, "id", "") or "")
        if not source_id:
            continue
        for raw_hint in (
            getattr(source, "label", None),
            getattr(source, "path", None),
            getattr(source, "href", None),
        ):
            for hint in _source_hints(raw_hint):
                source_by_hint.setdefault(hint, source_id)

    evidence_by_id = {
        str(getattr(entry, "id", "")): entry
        for entry in (getattr(snapshot, "evidence_map", []) or [])
        if getattr(entry, "id", None)
    }

    candidate_items = list(getattr(manifest, "charts", []) or []) + list(getattr(manifest, "tables", []) or [])
    for item in candidate_items:
        existing_source_id = str(getattr(item, "source_id", "") or "")
        if existing_source_id in source_ids:
            continue

        evidence = evidence_by_id.get(str(getattr(item, "id", "") or ""))
        hints = [
            getattr(item, "source_id", None),
            getattr(item, "title", None),
            getattr(item, "asset_path", None),
            getattr(evidence, "source_dataset", None) if evidence else None,
        ]
        source_id = _match_source_id(hints, source_by_hint)
        if source_id:
            setattr(item, "source_id", source_id)


def dedupe_appendix_visual_evidence(manifest: Any) -> None:
    """Remove appendix items already promoted through visual evidence blocks."""
    blocks = list(getattr(manifest, "blocks", []) or [])
    if not blocks:
        return

    chart_ids = {str(getattr(chart, "id", "")) for chart in (getattr(manifest, "charts", []) or [])}
    table_ids = {str(getattr(table, "id", "")) for table in (getattr(manifest, "tables", []) or [])}
    evidence_ids = chart_ids | table_ids
    if not evidence_ids:
        return

    promoted_ids: set[str] = set()
    for block in blocks:
        block_type = _enum_value(getattr(block, "type", ""))
        block_priority = getattr(block, "evidence_priority", "")
        is_visual = block_type in VISUAL_BLOCK_TYPES or (block_type == "chart" and block_priority == "primary")
        if not is_visual:
            continue
        promoted_ids.update(str(eid) for eid in (getattr(block, "evidence_ids", []) or []) if str(eid) in evidence_ids)
        chart_id = str(getattr(block, "chart_id", "") or "")
        if chart_id in evidence_ids:
            promoted_ids.add(chart_id)

    if not promoted_ids:
        return

    filtered_blocks = []
    removed_duplicate = False
    for block in blocks:
        block_type = _enum_value(getattr(block, "type", ""))
        block_priority = getattr(block, "evidence_priority", "")
        if block_priority == "appendix" and block_type in {"chart", "table"}:
            block_ids = set(str(eid) for eid in (getattr(block, "evidence_ids", []) or []))
            for attr_name in ("chart_id", "table_id"):
                attr_value = str(getattr(block, attr_name, "") or "")
                if attr_value:
                    block_ids.add(attr_value)
            if block_ids & promoted_ids:
                removed_duplicate = True
                continue
        filtered_blocks.append(block)

    if not removed_duplicate:
        return

    has_appendix_detail = any(
        getattr(block, "evidence_priority", "") == "appendix"
        and _enum_value(getattr(block, "type", "")) in {"chart", "table"}
        for block in filtered_blocks
    )
    if not has_appendix_detail:
        filtered_blocks = [
            block for block in filtered_blocks
            if not (
                getattr(block, "evidence_priority", "") == "appendix"
                and _enum_value(getattr(block, "type", "")) == "markdown"
                and "附录" in str(getattr(block, "body", "") or "")
            )
        ]

    manifest.blocks = filtered_blocks


def _source_hints(raw_hint: Any) -> list[str]:
    if raw_hint is None:
        return []
    text = str(raw_hint).strip()
    if not text:
        return []
    basename = Path(text).name
    hints = {text.lower(), basename.lower()}
    return [hint for hint in hints if hint]


def _match_source_id(raw_hints: list[Any], source_by_hint: dict[str, str]) -> str | None:
    for raw_hint in raw_hints:
        for hint in _source_hints(raw_hint):
            if hint in source_by_hint:
                return hint and source_by_hint[hint]
    return None
