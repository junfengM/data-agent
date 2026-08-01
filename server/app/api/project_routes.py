from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import (
    AnalysisProject,
    AnalysisProjectCreate,
    AnalysisProjectUpdate,
    OnboardingUpdate,
    ProjectContext,
    ProjectContextCreate,
    ProjectContextUpdate,
    SemanticLayerCreate,
    SemanticLayerResponse,
    SourceRoutingUpdate,
)
from app.tools.path_safety import PathSafetyError, resolve_project_yaml_path

router = APIRouter()


# ── Projects ──


@router.get("/projects", response_model=list[AnalysisProject])
def list_projects(include_archived: bool = False) -> list[AnalysisProject]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    return store.list_projects(include_archived=include_archived)


@router.post("/projects", response_model=AnalysisProject)
def create_project(project: AnalysisProjectCreate) -> AnalysisProject:
    if not project.name.strip():
        raise HTTPException(status_code=400, detail="Project name is required")

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    return store.create_project(project)


@router.get("/projects/{project_id}", response_model=AnalysisProject)
def get_project(project_id: str) -> AnalysisProject:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=AnalysisProject)
def update_project(project_id: str, project: AnalysisProjectUpdate) -> AnalysisProject:
    if project.name is not None and not project.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
    if project.status is not None and project.status not in {"active", "archived"}:
        raise HTTPException(status_code=400, detail="Project status must be active or archived")

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    updated = store.update_project(project_id, project)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


# ── Project Contexts ──


@router.get("/projects/{project_id}/contexts", response_model=list[ProjectContext])
def list_project_contexts(project_id: str) -> list[ProjectContext]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return store.list_project_contexts(project_id)


@router.post("/projects/{project_id}/contexts", response_model=ProjectContext)
def create_project_context(project_id: str, context: ProjectContextCreate) -> ProjectContext:
    if not context.title.strip():
        raise HTTPException(status_code=400, detail="Context title is required")
    if not context.body.strip():
        raise HTTPException(status_code=400, detail="Context body is required")

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    created = store.create_project_context(project_id, context)
    if created is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return created


@router.patch("/projects/{project_id}/contexts/{context_id}", response_model=ProjectContext)
def update_project_context(
    project_id: str, context_id: str, context: ProjectContextUpdate
) -> ProjectContext:
    if context.title is not None and not context.title.strip():
        raise HTTPException(status_code=400, detail="Context title cannot be empty")
    if context.body is not None and not context.body.strip():
        raise HTTPException(status_code=400, detail="Context body cannot be empty")

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    updated = store.update_project_context(project_id, context_id, context)
    if updated is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return updated


@router.delete("/projects/{project_id}/contexts/{context_id}", status_code=204)
def delete_project_context(project_id: str, context_id: str) -> Response:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    deleted = store.delete_project_context(project_id, context_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Context not found")
    return Response(status_code=204)


# ── Source Routing ──


@router.get("/projects/{project_id}/source-routing")
def get_source_routing(project_id: str) -> dict[str, str]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return store.get_source_routing(project_id)


@router.put("/projects/{project_id}/source-routing")
def update_source_routing(project_id: str, routing: SourceRoutingUpdate) -> dict[str, str]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    store.update_source_routing(project_id, {routing.category: routing.preference})
    return {routing.category: routing.preference}


# ── Semantic Layers ──


@router.get("/projects/{project_id}/semantic-layers", response_model=list[SemanticLayerResponse])
def list_semantic_layers(project_id: str) -> list[SemanticLayerResponse]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    layers = store.list_semantic_layers(project_id)
    return [SemanticLayerResponse(**layer) for layer in layers]


@router.post("/projects/{project_id}/semantic-layers", response_model=SemanticLayerResponse)
def create_semantic_layer(project_id: str, layer: SemanticLayerCreate) -> SemanticLayerResponse:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        layer_path = resolve_project_yaml_path(
            workspace_dir=settings.resolved_workspace_dir,
            project_id=project_id,
            requested_path=layer.path,
        )
    except PathSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    created = store.create_semantic_layer({
        "project_id": project_id,
        "name": layer.name,
        "path": str(layer_path),
    })
    return SemanticLayerResponse(**created)


@router.get("/projects/{project_id}/semantic-layers/active")
def get_active_semantic_layer(project_id: str) -> dict[str, object]:
    """Return the active semantic layer's full content (metrics, dimensions, caveats)."""
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layers = store.list_semantic_layers(project_id)
    if not layers:
        return {"metrics": [], "dimensions": [], "caveats": []}
    from app.tools.preflight import load_semantic_layer, select_active_layer
    active = select_active_layer(layers)
    if not active:
        return {"metrics": [], "dimensions": [], "caveats": []}
    sl = load_semantic_layer(Path(active["path"]))
    return {
        "id": active.get("id"),
        "name": active.get("name"),
        "path": active.get("path"),
        "is_active": active.get("is_active", False),
        "metrics": sl.metrics,
        "dimensions": sl.dimensions,
        "caveats": sl.caveats,
    }


@router.get("/projects/{project_id}/semantic-layers/{layer_id}")
def inspect_semantic_layer(project_id: str, layer_id: str) -> dict[str, object]:
    """Inspect a specific semantic layer's content."""
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layers = store.list_semantic_layers(project_id)
    layer = next((item for item in layers if item["id"] == layer_id), None)
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    from app.tools.preflight import load_semantic_layer
    sl = load_semantic_layer(Path(layer["path"]))
    return {"id": layer_id, "name": layer["name"], "metrics": sl.metrics, "dimensions": sl.dimensions, "caveats": sl.caveats}


@router.post("/projects/{project_id}/semantic-layers/{layer_id}/promote")
def promote_semantic_layer(project_id: str, layer_id: str) -> dict[str, object]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    success = store.promote_active_layer(project_id, layer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Layer not found for this project")
    return {"status": "ok", "active_layer_id": layer_id}


# ── Onboarding ──


@router.get("/projects/{project_id}/onboarding")
def get_onboarding_progress(project_id: str) -> dict[str, Any]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return store.get_onboarding_progress(project_id)


@router.put("/projects/{project_id}/onboarding")
def update_onboarding_progress(project_id: str, progress: OnboardingUpdate) -> dict[str, Any]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    store.update_onboarding_progress(project_id, progress.model_dump())
    return progress.model_dump()
