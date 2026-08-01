from fastapi import APIRouter, HTTPException, UploadFile

from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import DatasetRecord
from app.tools.files import UploadValidationError, save_upload

router = APIRouter()


@router.post("/files")
async def upload_file(file: UploadFile, project_id: str | None = None) -> dict[str, str]:
    settings = get_settings()
    try:
        saved = await save_upload(file, settings.resolved_workspace_dir / "uploads")
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store = MemoryStore(settings.resolved_sqlite_path)
    dataset_id = store.record_dataset(
        path=saved.path,
        filename=saved.filename,
        content_type=saved.content_type,
        project_id=project_id,
    )
    return {
        "dataset_id": dataset_id,
        "filename": saved.filename,
        "path": str(saved.path),
        "size_bytes": str(saved.size_bytes),
    }


@router.get("/datasets", response_model=list[DatasetRecord])
def list_datasets(project_id: str | None = None) -> list[DatasetRecord]:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    return store.list_datasets(project_id=project_id)


@router.post("/projects/{project_id}/files")
async def upload_project_file(project_id: str, file: UploadFile) -> dict[str, str]:
    """Upload a file scoped to a specific analysis project."""
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        saved = await save_upload(file, settings.resolved_workspace_dir / "uploads")
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dataset_id = store.record_dataset(
        path=saved.path,
        filename=saved.filename,
        content_type=saved.content_type,
        project_id=project_id,
    )
    return {
        "dataset_id": dataset_id,
        "filename": saved.filename,
        "path": str(saved.path),
        "size_bytes": str(saved.size_bytes),
    }
