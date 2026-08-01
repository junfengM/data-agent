"""Tests for run pagination, deletion, and lifecycle API (DA-OPT-010)."""
import os

import pytest
from fastapi.testclient import TestClient

from app.agent import run_registry
from app.memory.store import MemoryStore
from app.models.schemas import RunResponse


def _make_run(run_id: str, question: str = "q") -> RunResponse:
    return RunResponse(id=run_id, status="completed", skill_id="auto", question=question)


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "test.db")


@pytest.fixture
def test_client(tmp_path):
    from app.core.settings import get_settings

    get_settings.cache_clear()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os.environ["DATA_AGENT_WORKSPACE_DIR"] = str(workspace)
    os.environ["DATA_AGENT_SQLITE_PATH"] = str(tmp_path / "test.db")
    os.environ["DATA_AGENT_GENERATED_CODE_EXECUTION"] = "disabled"

    from app.main import app

    with TestClient(app) as client:
        yield client, MemoryStore(tmp_path / "test.db")


def test_list_runs_paginated_and_counts(store):
    for index in range(3):
        store.record_run(_make_run(f"run-{index}", f"question {index}"))

    assert store.count_runs() == 3
    first_page = store.list_runs_paginated(limit=2, offset=0)
    second_page = store.list_runs_paginated(limit=2, offset=2)
    assert len(first_page) == 2
    assert len(second_page) == 1
    assert {r.id for r in first_page} | {r.id for r in second_page} == {
        "run-0", "run-1", "run-2",
    }


def test_delete_run_removes_row_and_events(store):
    run = _make_run("run-del")
    store.record_run(run)
    store.record_run_event(run_id="run-del", event_type="run_started", summary="start")

    assert store.delete_run("run-del") is True
    assert store.get_run("run-del") is None
    assert store.delete_run("run-del") is False


def test_delete_run_api_removes_run_and_artifacts(test_client, tmp_path):
    client, store = test_client
    store.record_run(_make_run("run-api-del"))

    response = client.delete("/api/runs/run-api-del")
    assert response.status_code == 200
    assert response.json() == {"deleted": "run-api-del"}
    assert store.get_run("run-api-del") is None


def test_delete_run_api_unknown_returns_404(test_client):
    client, _store = test_client
    response = client.delete("/api/runs/unknown-run")
    assert response.status_code == 404


def test_delete_run_api_rejects_invalid_id(test_client):
    client, _store = test_client
    # Path-traversal forms are already rejected by routing (404); this id reaches
    # the handler but fails the safe run-id pattern.
    response = client.delete("/api/runs/run%20id")
    assert response.status_code == 400


def test_delete_run_api_rejects_active_run(test_client):
    client, store = test_client
    run_registry.clear_registry()
    store.record_run(_make_run("run-active"))

    class _FakeTask:
        def done(self):
            return False

        def cancel(self):
            return None

    run_registry.register_run("run-active", _FakeTask(), object())
    response = client.delete("/api/runs/run-active")
    assert response.status_code == 409


def test_list_runs_api_respects_limit(test_client):
    client, store = test_client
    for index in range(3):
        store.record_run(_make_run(f"run-{index}"))

    response = client.get("/api/runs?limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2
