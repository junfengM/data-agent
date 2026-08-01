from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query

from app.core.model_config import ModelConfigRegistry
from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import DatasetRecord
from app.tools.preflight import select_active_layer
from app.tools.semantic_inference import (
    SemanticDraft,
    SemanticDraftRequest,
    SemanticDraftUpdate,
    build_semantic_dataset_profile,
    infer_semantic_draft_with_llm,
    semantic_draft_to_layer_payload,
    validate_semantic_draft,
)
from app.tools.semantic_validation import (
    SemanticMergePreview,
    precheck_semantic_layer_merge,
)

router = APIRouter()


@router.post("/projects/{project_id}/datasets/{dataset_id}/semantic-draft", response_model=SemanticDraft)
async def create_semantic_draft(
    project_id: str,
    dataset_id: str,
    request: SemanticDraftRequest | None = None,
) -> SemanticDraft:
    """Generate an unconfirmed semantic draft for one uploaded Excel/CSV dataset."""
    request = request or SemanticDraftRequest()
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _require_project(store, project_id)
    dataset = _require_dataset(store, dataset_id, project_id)

    profile = build_semantic_dataset_profile(dataset)
    if profile.get("error"):
        raise HTTPException(status_code=400, detail=profile["error"])

    contexts = store.list_project_contexts(project_id)
    model_config = None
    if request.use_llm:
        try:
            registry = ModelConfigRegistry(settings.resolved_config_dir / "models.yaml")
            model_config = registry.get_model(request.model_config_id)
        except Exception:
            model_config = None

    draft = await infer_semantic_draft_with_llm(
        profile=profile,
        project_id=project_id,
        project_contexts=contexts,
        model_config=model_config,
        use_llm=request.use_llm,
    )
    _write_draft(settings.resolved_workspace_dir, draft)
    return draft


@router.get("/projects/{project_id}/semantic-drafts/{draft_id}", response_model=SemanticDraft)
def get_semantic_draft(project_id: str, draft_id: str) -> SemanticDraft:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _require_project(store, project_id)
    return _read_draft(settings.resolved_workspace_dir, project_id, draft_id)


@router.patch("/projects/{project_id}/semantic-drafts/{draft_id}", response_model=SemanticDraft)
def update_semantic_draft(
    project_id: str,
    draft_id: str,
    update: SemanticDraftUpdate,
) -> SemanticDraft:
    """Persist user edits to an unconfirmed semantic draft."""
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _require_project(store, project_id)
    draft = _read_draft(settings.resolved_workspace_dir, project_id, draft_id)

    merged_payload = draft.model_dump(mode="json")
    merged_payload.update(update.model_dump(exclude_unset=True, mode="json"))
    draft = SemanticDraft.model_validate(merged_payload)

    dataset = _require_dataset(store, draft.dataset_id, project_id)
    profile = build_semantic_dataset_profile(dataset)
    draft = validate_semantic_draft(draft, profile=profile)
    _write_draft(settings.resolved_workspace_dir, draft)
    return draft


@router.post("/projects/{project_id}/semantic-drafts/{draft_id}/confirm")
def confirm_semantic_draft(
    project_id: str,
    draft_id: str,
    dry_run: bool = Query(False, description="If true, return merge preview without writing."),
) -> dict[str, Any]:
    """Confirm a draft and write it into the project's active semantic layer YAML.

    With ?dry_run=true, returns a merge preview without modifying any files.
    On blockers: returns 409 with conflict details.
    """
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _require_project(store, project_id)
    draft = _read_draft(settings.resolved_workspace_dir, project_id, draft_id)

    dataset = _require_dataset(store, draft.dataset_id, project_id)
    profile = build_semantic_dataset_profile(dataset)
    draft = validate_semantic_draft(draft, profile=profile)
    draft.status = "confirmed"

    layer_path, layer_id = _resolve_or_create_active_layer(
        store=store,
        workspace_dir=settings.resolved_workspace_dir,
        project_id=project_id,
    )
    layer_payload = semantic_draft_to_layer_payload(draft)

    # ── Load existing layer ──
    existing_layer: dict[str, Any] = {}
    if layer_path.exists():
        try:
            loaded = yaml.safe_load(layer_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                existing_layer = loaded
        except Exception:
            existing_layer = {}

    # ── Run precheck ──
    preview = precheck_semantic_layer_merge(
        existing_layer=existing_layer,
        incoming_payload=layer_payload,
    )

    if dry_run:
        return {
            "status": "preview",
            "draft_id": draft.id,
            "layer_id": layer_id,
            "can_confirm": preview.can_confirm,
            "blockers": [
                {
                    "name": b.metric_name,
                    "type": b.conflict_type,
                    "severity": b.severity,
                    "description": b.description,
                    "repair_action": b.repair_action,
                    "suggested_resolution": b.suggested_resolution,
                }
                for b in preview.blockers
            ],
            "warnings": [
                {
                    "name": w.metric_name,
                    "type": w.conflict_type,
                    "severity": w.severity,
                    "description": w.description,
                    "repair_action": w.repair_action,
                    "suggested_resolution": w.suggested_resolution,
                }
                for w in preview.warnings
            ],
            "incoming_metrics": preview.incoming_metrics,
            "would_replace": preview.would_replace,
            "would_add": preview.would_add,
            "would_keep": preview.would_keep,
            "requires_user_confirmation": preview.requires_user_confirmation,
        }

    # ── Block on blockers ──
    if not preview.can_confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "semantic_merge_blocked",
                "message": f"Cannot confirm: {len(preview.blockers)} blocker(s) found. "
                           "Use ?dry_run=true to preview conflicts, fix the draft, and re-confirm.",
                "blockers": [
                    {
                        "name": b.metric_name,
                        "type": b.conflict_type,
                        "severity": b.severity,
                        "description": b.description,
                        "suggested_resolution": b.suggested_resolution,
                    }
                    for b in preview.blockers
                ],
            },
        )

    # ── Merge and write ──
    merged = _merge_layer_payload(layer_path, layer_payload, source_dataset=draft.filename)
    layer_path.parent.mkdir(parents=True, exist_ok=True)
    layer_path.write_text(
        yaml.dump(merged, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    _write_draft(settings.resolved_workspace_dir, draft)
    return {
        "status": "confirmed",
        "draft_id": draft.id,
        "layer_id": layer_id,
        "layer_path": str(layer_path),
        "metrics_written": len(layer_payload.get("metrics", [])),
        "dimensions_written": len(layer_payload.get("dimensions", [])),
        "would_replace": preview.would_replace,
        "would_add": preview.would_add,
        "warnings": [
            {"name": w.metric_name, "type": w.conflict_type, "description": w.description}
            for w in preview.warnings
        ] if preview.warnings else [],
    }


@router.get("/projects/{project_id}/semantic-drafts", response_model=list[SemanticDraft])
def list_semantic_drafts(project_id: str) -> list[SemanticDraft]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _require_project(store, project_id)
    draft_dir = _draft_dir(settings.resolved_workspace_dir, project_id)
    if not draft_dir.exists():
        return []
    drafts: list[SemanticDraft] = []
    for path in sorted(draft_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            drafts.append(SemanticDraft.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return drafts


def _require_project(store: MemoryStore, project_id: str) -> None:
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _require_dataset(store: MemoryStore, dataset_id: str, project_id: str) -> DatasetRecord:
    dataset = store.get_dataset(dataset_id, project_id=project_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found for this project")
    return dataset


def _draft_dir(workspace_dir: Path, project_id: str) -> Path:
    return workspace_dir / "projects" / project_id / "semantic-drafts"


def _draft_path(workspace_dir: Path, project_id: str, draft_id: str) -> Path:
    if not draft_id or "/" in draft_id or ".." in draft_id:
        raise HTTPException(status_code=400, detail="Invalid draft id")
    return _draft_dir(workspace_dir, project_id) / f"{draft_id}.json"


def _write_draft(workspace_dir: Path, draft: SemanticDraft) -> None:
    path = _draft_path(workspace_dir, draft.project_id, draft.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")


def _read_draft(workspace_dir: Path, project_id: str, draft_id: str) -> SemanticDraft:
    path = _draft_path(workspace_dir, project_id, draft_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Semantic draft not found")
    try:
        draft = SemanticDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid semantic draft file: {exc}") from exc
    if draft.project_id != project_id:
        raise HTTPException(status_code=404, detail="Semantic draft not found")
    return draft


def _resolve_or_create_active_layer(
    *,
    store: MemoryStore,
    workspace_dir: Path,
    project_id: str,
) -> tuple[Path, str]:
    layers = store.list_semantic_layers(project_id)
    active = select_active_layer(layers)
    if active:
        if not active.get("is_active"):
            store.promote_active_layer(project_id, active["id"])
        return Path(active["path"]), active["id"]

    layer_path = workspace_dir / "projects" / project_id / "semantic-layer.yaml"
    created = store.create_semantic_layer({
        "project_id": project_id,
        "name": "Confirmed Upload Semantics",
        "path": str(layer_path),
    })
    store.promote_active_layer(project_id, created["id"])
    return layer_path, created["id"]


def _merge_layer_payload(layer_path: Path, incoming: dict[str, Any], *, source_dataset: str) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if layer_path.exists():
        try:
            loaded = yaml.safe_load(layer_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}

    def keep_existing(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        kept: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("source_dataset") == source_dataset or item.get("source_table") == source_dataset:
                continue
            kept.append(item)
        return kept

    merged = dict(existing)
    merged["metrics"] = keep_existing(existing.get("metrics")) + incoming.get("metrics", [])
    merged["dimensions"] = keep_existing(existing.get("dimensions")) + incoming.get("dimensions", [])
    existing_sources = [
        s for s in existing.get("sources", [])
        if isinstance(s, dict) and s.get("name") != source_dataset
    ]
    merged["sources"] = existing_sources + incoming.get("sources", [])
    existing_caveats = existing.get("caveats") if isinstance(existing.get("caveats"), list) else []
    merged["caveats"] = existing_caveats + incoming.get("caveats", [])
    return merged
