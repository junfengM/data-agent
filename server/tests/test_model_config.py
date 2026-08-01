from pathlib import Path

import pytest

from app.core.model_config import ModelConfigRegistry


def write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_model_config_registry_rejects_non_mapping_top_level(tmp_path):
    config_path = write_config(tmp_path / "models.yaml", "- not\n- mapping\n")

    with pytest.raises(ValueError, match="top-level YAML must be an object"):
        ModelConfigRegistry(config_path)


def test_model_config_registry_rejects_non_mapping_models(tmp_path):
    config_path = write_config(tmp_path / "models.yaml", "models:\n  - gpt\n")
    registry = ModelConfigRegistry(config_path)

    with pytest.raises(ValueError, match="'models' must be an object"):
        registry.list_models()


def test_model_config_registry_rejects_missing_api_key_env(tmp_path):
    config_path = write_config(
        tmp_path / "models.yaml",
        "models:\n  gpt-test:\n    provider: openai\n    model: gpt-test\n",
    )
    registry = ModelConfigRegistry(config_path)

    with pytest.raises(ValueError, match="missing 'api_key_env'"):
        registry.list_models()


def test_get_model_reports_missing_model_id(tmp_path):
    config_path = write_config(
        tmp_path / "models.yaml",
        "models:\n  gpt:\n    provider: openai\n    model: gpt-4\n    api_key_env: OPENAI_API_KEY\n",
    )
    registry = ModelConfigRegistry(config_path)

    with pytest.raises(ValueError, match="Unknown model config: nonexistent-model"):
        registry.get_model("nonexistent-model")


def test_get_model_returns_default_when_id_is_none(tmp_path):
    config_path = write_config(
        tmp_path / "models.yaml",
        "default_model: gpt\nmodels:\n  gpt:\n    provider: openai\n    model: gpt-4\n    api_key_env: OPENAI_API_KEY\n",
    )
    registry = ModelConfigRegistry(config_path)

    model = registry.get_model(None)

    assert model.id == "gpt"
    assert model.model == "gpt-4"


def test_default_model_is_none_when_not_configured(tmp_path):
    config_path = write_config(
        tmp_path / "models.yaml",
        "models:\n  gpt:\n    provider: openai\n    model: gpt-4\n    api_key_env: OPENAI_API_KEY\n",
    )
    registry = ModelConfigRegistry(config_path)

    assert registry.default_model is None


def test_bad_yaml_raises_clear_error(tmp_path):
    config_path = write_config(
        tmp_path / "models.yaml",
        "models: [this is: bad yaml: syntax\n",
    )

    with pytest.raises(Exception):
        ModelConfigRegistry(config_path)
