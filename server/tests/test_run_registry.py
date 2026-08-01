"""Tests for the in-flight run registry and cancel route."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.agent import run_registry


@pytest.fixture
def test_client(tmp_path):
    from app.core.settings import get_settings

    get_settings.cache_clear()
    os_env_workspace = tmp_path / "workspace"
    os_env_workspace.mkdir()
    import os

    os.environ["DATA_AGENT_WORKSPACE_DIR"] = str(os_env_workspace)
    os.environ["DATA_AGENT_SQLITE_PATH"] = str(tmp_path / "test.db")
    os.environ["DATA_AGENT_GENERATED_CODE_EXECUTION"] = "disabled"

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.anyio
async def test_register_and_cancel_task():
    run_registry.clear_registry()

    async def sleeper():
        await asyncio.sleep(60)

    task = asyncio.create_task(sleeper())
    run_registry.register_run("run-1", task, object())
    assert "run-1" in run_registry.active_run_ids()

    assert run_registry.cancel_run("run-1") is True
    with pytest.raises(asyncio.CancelledError):
        await task

    run_registry.unregister_run("run-1")
    assert run_registry.cancel_run("run-1") is False
    assert run_registry.active_run_ids() == []


def test_cancel_route_contract(test_client, monkeypatch):
    monkeypatch.setattr(
        "app.agent.run_registry.cancel_run", lambda run_id: True
    )
    response = test_client.post("/api/runs/abc/cancel")
    assert response.status_code == 200
    assert response.json() == {"run_id": "abc", "status": "cancelled"}


def test_cancel_route_unknown_run_returns_404(test_client):
    run_registry.clear_registry()
    response = test_client.post("/api/runs/unknown/cancel")
    assert response.status_code == 404
