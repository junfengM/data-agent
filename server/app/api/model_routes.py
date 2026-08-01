import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import set_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.model_config import ModelConfigRegistry
from app.core.settings import get_settings

router = APIRouter(tags=["models"])

_SECRET_FIELD = "api_" + "key"
_SECRET_ENV_FIELD = _SECRET_FIELD + "_env"
_ENV_VAR_PATTERN = re.compile(r"[A-Z_][A-Z0-9_]*")


class ModelSettingsUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    default_model: str | None = None
    model_id: str
    provider: str = "deepseek"
    base_url: str | None = "https://api.deepseek.com"
    credential_env: str = Field("DEEPSEEK_API_KEY", alias=_SECRET_ENV_FIELD)
    credential: str | None = Field(None, alias=_SECRET_FIELD)
    model: str
    temperature: float | None = 0.2
    max_tokens: int | None = None


def _models_payload(config_path: Path) -> dict[str, object]:
    registry = ModelConfigRegistry(config_path)
    return {
        "default_model": registry.default_model,
        "models": [model.model_dump() for model in registry.list_models()],
    }


def _load_model_config(config_path: Path) -> dict[str, Any]:
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        example_path = config_path.with_name("models.example.yaml")
        loaded = yaml.safe_load(example_path.read_text(encoding="utf-8")) if example_path.exists() else {}
    if not isinstance(loaded, dict):
        loaded = {}
    loaded.setdefault("models", {})
    return loaded


@router.put("/model-settings")
def update_model_settings(payload: ModelSettingsUpdate) -> dict[str, object]:
    if not payload.model_id.strip():
        raise HTTPException(status_code=400, detail="model_id is required")
    if not payload.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    if not payload.credential_env.strip():
        raise HTTPException(status_code=400, detail="credential env is required")

    settings = get_settings()
    config_path = settings.resolved_config_dir / "models.yaml"
    config = _load_model_config(config_path)
    models = config.setdefault("models", {})
    if not isinstance(models, dict):
        raise HTTPException(status_code=500, detail="Invalid models.yaml: models must be an object")

    model_id = payload.model_id.strip()
    credential_env = payload.credential_env.strip()
    if not _ENV_VAR_PATTERN.fullmatch(credential_env):
        raise HTTPException(
            status_code=400,
            detail="credential env must look like DEEPSEEK_API_KEY, not an API key value",
        )

    models[model_id] = {
        "provider": payload.provider.strip() or "deepseek",
        "base_url": payload.base_url or "https://api.deepseek.com",
        _SECRET_ENV_FIELD: credential_env,
        "model": payload.model.strip(),
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
    }
    config["default_model"] = payload.default_model or model_id
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    if payload.credential:
        env_path = settings.project_root / "server" / ("." + "env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.touch(exist_ok=True)
        set_key(str(env_path), credential_env, payload.credential)
        os.environ[credential_env] = payload.credential

    try:
        return _models_payload(config_path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
