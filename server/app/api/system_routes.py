from fastapi import APIRouter

from app.core.settings import get_settings
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/settings")
def get_execution_settings() -> dict[str, str]:
    settings = get_settings()
    return {
        "generated_code_execution": settings.generated_code_execution,
    }
