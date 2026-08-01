import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.models.schemas import ModelConfigSummary


class ModelConfigRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._payload = self._load()

    @property
    def default_model(self) -> str | None:
        value = self._payload.get("default_model")
        return str(value) if value else None

    def list_models(self) -> list[ModelConfigSummary]:
        models = self._payload.get("models", {})
        if not isinstance(models, dict):
            raise ValueError(f"Invalid model config in {self.path}: 'models' must be an object")

        summaries: list[ModelConfigSummary] = []
        for model_id, config in sorted(models.items()):
            if not isinstance(config, dict):
                raise ValueError(
                    f"Invalid model config '{model_id}' in {self.path}: entry must be an object"
                )

            try:
                api_key_env = str(config["api_key_env"])
                summaries.append(
                    ModelConfigSummary(
                        id=str(model_id),
                        api_key_configured=bool(os.getenv(api_key_env)),
                        **config,
                    )
                )
            except KeyError as exc:
                raise ValueError(
                    f"Invalid model config '{model_id}' in {self.path}: missing {exc.args[0]!r}"
                ) from exc
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid model config '{model_id}' in {self.path}: {exc}"
                ) from exc
        return summaries

    def get_model(self, model_id: str | None = None) -> ModelConfigSummary:
        target_id = model_id or self.default_model
        for model in self.list_models():
            if model.id == target_id:
                return model
        raise ValueError(f"Unknown model config: {target_id}")

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            example_path = self.path.with_name("models.example.yaml")
            if example_path.exists():
                return _load_yaml_mapping(example_path)
            return {"models": {}}
        return _load_yaml_mapping(self.path)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid model config in {path}: top-level YAML must be an object")
    return loaded
