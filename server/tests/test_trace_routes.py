from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client(tmp_path):
    import os

    from app.core.settings import get_settings
    get_settings.cache_clear()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = tmp_path / "test.db"

    os.environ["DATA_AGENT_WORKSPACE_DIR"] = str(workspace)
    os.environ["DATA_AGENT_SQLITE_PATH"] = str(db_path)
    os.environ["DATA_AGENT_GENERATED_CODE_EXECUTION"] = "disabled"

    from app.main import app
    from app.memory.store import MemoryStore
    from app.models.schemas import (
        Artifact,
        ArtifactType,
        RunResponse,
    )

    store = MemoryStore(db_path)
    run = RunResponse(
        id="test-run-001",
        status="completed",
        skill_id="test-skill",
        question="Test question",
        project_id="test-project",
        artifacts=[
            Artifact(type=ArtifactType.table, title="Test Table"),
            Artifact(type=ArtifactType.chart, title="Test Chart"),
        ],
        tool_calls=[],
        workflow_steps=[],
        validation_results=[],
        validation_passed=True,
    )
    store.record_run(run)

    # Save some runtime events including length truncation
    events = [
        ("llm_request_started", "开始请求", {"iteration": 1}),
        ("llm_request_completed", "完成请求", {"iteration": 1, "finish_reason": "length"}),
        ("llm_request_completed", "完成请求", {"iteration": 2, "finish_reason": "length"}),
        ("planner_final_payload_parsed", "Payload解析", {"report_md_chars": 19}),
    ]
    for event_type, summary, data in events:
        store.record_run_event("test-run-001", event_type, summary, data)

    return TestClient(app)


class TestExportSchemaV2Compatibility:
    def test_has_legacy_fields(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export")
        assert response.status_code == 200
        payload = response.json()
        assert "run" in payload
        assert "events" in payload
        assert "derived_trace" in payload
        assert "diagnostic_summary" in payload

    def test_has_new_fields(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export")
        assert response.status_code == 200
        payload = response.json()
        assert "llm_diagnostics" in payload
        assert "finalizer_diagnostics" in payload
        assert "context_budget_summary" in payload
        assert "artifact_binding_summary" in payload
        assert "failure_analysis" in payload

    def test_llm_tuning_log_endpoint(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/llm")
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == 1
        assert payload["summary"]["request_count"] == 2
        assert payload["summary"]["length_truncation_count"] == 2
        assert payload["rounds"][0]["iteration"] == 1
        assert "tuning_notes" in payload

    def test_llm_tuning_log_export(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/llm/export")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "data-agent-llm-tuning-test-run" in response.headers["content-disposition"]

    def test_schema_version_is_2(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export")
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == 2

    def test_repeated_length_truncation_classified(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export")
        assert response.status_code == 200
        payload = response.json()
        diagnostic = payload["diagnostic_summary"]
        assert diagnostic["likely_failure_mode"] == "repeated_finalizer_length_truncation"
        assert diagnostic["empty_or_tiny_report"] is True

    def test_evidence_generated_but_empty_report(self, test_client, tmp_path):
        import os
        from app.core.settings import get_settings
        get_settings.cache_clear()

        workspace = tmp_path / "workspace2"
        workspace.mkdir()
        db_path = tmp_path / "test2.db"

        os.environ["DATA_AGENT_WORKSPACE_DIR"] = str(workspace)
        os.environ["DATA_AGENT_SQLITE_PATH"] = str(db_path)

        from app.main import app
        from app.memory.store import MemoryStore
        from app.models.schemas import Artifact, ArtifactType, RunResponse

        store = MemoryStore(db_path)
        run = RunResponse(
            id="test-run-002",
            status="completed",
            skill_id="test-skill",
            question="Evidence test",
            project_id="test-project",
            artifacts=[
                Artifact(type=ArtifactType.table, title="Table"),
                Artifact(type=ArtifactType.chart, title="Chart"),
            ],
            tool_calls=[],
            workflow_steps=[],
            validation_results=[],
            validation_passed=False,
        )
        store.record_run(run)
        events = [
            ("planner_final_payload_parsed", "Payload解析", {"report_md_chars": 100}),
        ]
        for event_type, summary, data in events:
            store.record_run_event("test-run-002", event_type, summary, data)

        client = TestClient(app)
        response = client.get("/api/runs/test-run-002/trace/export")
        assert response.status_code == 200
        payload = response.json()
        diagnostic = payload["diagnostic_summary"]
        assert diagnostic["evidence_generation_completed"] is True
        assert diagnostic["table_artifact_count"] > 0
        assert diagnostic["chart_artifact_count"] > 0
        assert diagnostic["final_report_chars"] == 100
        assert diagnostic["empty_or_tiny_report"] is True


class TestRedaction:
    def test_api_key_redacted(self, test_client, tmp_path):
        import os
        from app.core.settings import get_settings
        get_settings.cache_clear()

        db_path = tmp_path / "redact.db"
        os.environ["DATA_AGENT_SQLITE_PATH"] = str(db_path)

        from app.main import app
        from app.memory.store import MemoryStore
        from app.models.schemas import Artifact, ArtifactType, RunResponse

        store = MemoryStore(db_path)
        run = RunResponse(
            id="test-run-redact",
            status="completed",
            skill_id="test-skill",
            question="Redact test",
            project_id="test-project",
            artifacts=[],
            tool_calls=[],
            workflow_steps=[],
            validation_results=[],
            validation_passed=True,
        )
        store.record_run(run)
        store.record_run_event(
            "test-run-redact",
            "llm_request_started",
            "开始请求",
            {
                "api_key": "sk-secret-key-12345",
                "authorization": "Bearer token-123",
                "password": "my-password",
                "secret": "my-secret",
                "token": "my-token",
                "refresh_token": "my-refresh",
                "model_config": {
                    "api_key": "sk-another-key",
                },
            },
        )

        client = TestClient(app)
        response = client.get("/api/runs/test-run-redact/trace/export")
        assert response.status_code == 200
        payload = response.json()
        payload_str = json.dumps(payload)
        assert "sk-secret-key-12345" not in payload_str
        assert "my-password" not in payload_str
        assert "my-secret" not in payload_str
        assert "my-token" not in payload_str
        assert "my-refresh" not in payload_str
        assert "Bearer token-123" not in payload_str
        assert "sk-another-key" not in payload_str


class TestLevelParameter:
    def test_default_level_is_diagnostic(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export")
        assert response.status_code == 200
        payload = response.json()
        assert "diagnostic_summary" in payload
        assert "failure_analysis" in payload

    def test_normal_level(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export?level=normal")
        assert response.status_code == 200
        payload = response.json()
        assert "diagnostic_summary" in payload

    def test_diagnostic_level(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export?level=diagnostic")
        assert response.status_code == 200
        payload = response.json()
        assert "diagnostic_summary" in payload

    def test_invalid_level(self, test_client):
        response = test_client.get("/api/runs/test-run-001/trace/export?level=invalid")
        assert response.status_code == 400
