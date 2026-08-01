"""Regression tests for explicit temperature=0 configuration (DA-OPT-007)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.llm import LLMClient, resolve_temperature
from app.models.schemas import ModelConfigSummary


def test_resolve_temperature_preserves_explicit_zero():
    assert resolve_temperature(0.0) == 0.0
    assert resolve_temperature(0.0, default=0.3) == 0.0


def test_resolve_temperature_falls_back_only_when_unset():
    assert resolve_temperature(None) == 0.2
    assert resolve_temperature(None, default=0.3) == 0.3
    assert resolve_temperature(0.7) == 0.7


@pytest.mark.anyio
async def test_llm_client_sends_configured_zero_temperature(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "fake-key")
    config = ModelConfigSummary(
        id="t0",
        provider="openai",
        base_url="https://example.invalid/v1",
        api_key_env="TEST_API_KEY",
        model="gpt-x",
        temperature=0.0,
    )
    client = LLMClient(config)

    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
    )
    client.client = fake

    await client.complete("system", "user")

    kwargs = fake.chat.completions.create.await_args.kwargs
    assert kwargs["temperature"] == 0.0


@pytest.mark.anyio
async def test_llm_client_uses_default_when_temperature_unset(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "fake-key")
    config = ModelConfigSummary(
        id="t1",
        provider="openai",
        base_url="https://example.invalid/v1",
        api_key_env="TEST_API_KEY",
        model="gpt-x",
        temperature=None,
    )
    client = LLMClient(config)

    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
    )
    client.client = fake

    await client.complete("system", "user")

    kwargs = fake.chat.completions.create.await_args.kwargs
    assert kwargs["temperature"] == 0.2
