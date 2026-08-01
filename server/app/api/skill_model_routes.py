from fastapi import APIRouter, HTTPException

from app.agent.orchestrator import AgentOrchestrator
from app.core.model_config import ModelConfigRegistry
from app.core.settings import get_settings
from app.models.schemas import SkillSummary

router = APIRouter()


@router.get("/skills", response_model=list[SkillSummary])
def list_skills() -> list[SkillSummary]:
    orchestrator = AgentOrchestrator.from_settings(get_settings())
    return orchestrator.skill_registry.list_skills()


@router.get("/models")
def list_models() -> dict[str, object]:
    settings = get_settings()
    registry = ModelConfigRegistry(settings.resolved_config_dir / "models.yaml")
    try:
        models = registry.list_models()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "default_model": registry.default_model,
        "models": [model.model_dump() for model in models],
    }
