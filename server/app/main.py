from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parents[1]
SERVER_ENV_FILE = SERVER_DIR / ("." + "env")
load_dotenv(SERVER_ENV_FILE)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dataset_routes import router as dataset_router
from app.api.model_routes import router as model_router
from app.api.project_routes import router as project_router
from app.api.run_routes import router as run_router
from app.api.semantic_routes import router as semantic_router
from app.api.skill_model_routes import router as skill_model_router
from app.api.stream_routes import router as stream_router
from app.api.system_routes import router as system_router
from app.api.trace_routes import router as trace_router
from app.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Data Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(trace_router, prefix="/api")
    app.include_router(stream_router, prefix="/api")
    app.include_router(semantic_router, prefix="/api")
    app.include_router(model_router, prefix="/api")
    app.include_router(skill_model_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(project_router, prefix="/api")
    app.include_router(dataset_router, prefix="/api")
    app.include_router(run_router, prefix="/api")
    return app


app = create_app()
