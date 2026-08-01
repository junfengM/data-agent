from fastapi.testclient import TestClient
from pathlib import Path
import io
import json
import pytest


@pytest.fixture
def test_client(tmp_path):
    """Create a TestClient with temp workspace and db."""
    import os

    # Clear cached settings so new env vars are picked up by each test
    from app.core.settings import get_settings

    get_settings.cache_clear()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = tmp_path / "test.db"

    # Set env vars so app uses temp paths
    os.environ["DATA_AGENT_WORKSPACE_DIR"] = str(workspace)
    os.environ["DATA_AGENT_SQLITE_PATH"] = str(db_path)
    os.environ["DATA_AGENT_GENERATED_CODE_EXECUTION"] = "disabled"

    from app.main import app
    from app.memory.store import MemoryStore
    from app.models.schemas import (
        RunResponse,
        Artifact,
        ArtifactType,
        ArtifactManifest,
        ArtifactSnapshot,
        ArtifactBlock,
        ArtifactBlockType,
    )

    # Create a run with visual_report artifact
    store = MemoryStore(db_path)
    manifest = ArtifactManifest(
        title="Test Report",
        blocks=[
            ArtifactBlock(id="b1", type=ArtifactBlockType.markdown, body="# Hello"),
        ],
    )
    snapshot = ArtifactSnapshot(datasets={"ds1": [{"x": 1}]})
    artifact = Artifact(
        type=ArtifactType.visual_report,
        title="图文分析报告",
        content="# Hello",
        data={
            "manifest": manifest.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        },
    )
    run = RunResponse(
        id="test-run-001",
        status="completed",
        skill_id="product-analysis",
        question="Test question",
        project_id="proj-1",
        artifacts=[artifact],
    )
    store.record_run(run)
    store.record_run_event(
        run.id,
        event_type="llm_request_completed",
        summary="Model returned a tool call",
        data={
            "iteration": 1,
            "duration_ms": 250,
            "requested_tools": ["execute_code"],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
        },
        elapsed_ms=300,
    )
    run_dir = workspace / "artifacts" / run.id
    run_dir.mkdir(parents=True)
    (run_dir / "revenue-trend.html").write_text(
        "<!doctype html><html><body><script>document.body.dataset.ready='1'</script></body></html>",
        encoding="utf-8",
    )
    (run_dir / "revenue-share.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    yield TestClient(app)

    # Cleanup env
    for key in [
        "DATA_AGENT_WORKSPACE_DIR",
        "DATA_AGENT_SQLITE_PATH",
        "DATA_AGENT_GENERATED_CODE_EXECUTION",
    ]:
        os.environ.pop(key, None)


def test_export_manifest_run_returns_200(test_client):
    response = test_client.get("/api/runs/test-run-001/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "manifest" in data
    assert "snapshot" in data
    assert "metadata" in data
    assert data["manifest"]["title"] == "Test Report"


def test_export_diagnostic_trace_returns_ai_readable_json(test_client):
    response = test_client.get("/api/runs/test-run-001/trace/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["schema_version"] == 2
    assert data["run"]["id"] == "test-run-001"
    assert data["diagnostic_summary"]["event_count"] == 1
    assert data["events"][0]["type"] == "llm_request_completed"
    assert data["events"][0]["data"]["requested_tools"] == ["execute_code"]
    assert data["events"][0]["data"]["usage"]["prompt_tokens"] == 1200
    assert "api_key" not in json.dumps(data).lower()


def test_export_missing_run_returns_404(test_client):
    response = test_client.get("/api/runs/nonexistent/export")
    assert response.status_code == 404


def test_run_report_asset_returns_inline_html_with_sandbox_headers(test_client):
    response = test_client.get("/api/runs/test-run-001/assets/revenue-trend.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == 'inline; filename="revenue-trend.html"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "connect-src 'none'" in response.headers["content-security-policy"]
    assert 'id="data-agent-chart-reader"' in response.text
    assert "displayModeBar: false" in response.text
    assert 'axis.type = "category"' in response.text
    assert "axis.categoryarray = uniqueValues" in response.text
    assert response.text.index('id="data-agent-chart-reader"') < response.text.index("</body>")


def test_run_report_asset_returns_image(test_client):
    response = test_client.get("/api/runs/test-run-001/assets/revenue-share.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_run_report_asset_rejects_unsupported_type(test_client):
    response = test_client.get("/api/runs/test-run-001/assets/analysis-notebook.ipynb")

    assert response.status_code == 400


def test_run_report_asset_missing_file_returns_404(test_client):
    response = test_client.get("/api/runs/test-run-001/assets/missing.html")

    assert response.status_code == 404


def test_export_run_without_manifest_returns_400(test_client):
    import os

    # Create a run without visual_report
    from app.memory.store import MemoryStore
    from app.models.schemas import RunResponse, Artifact, ArtifactType

    store = MemoryStore(Path(os.environ["DATA_AGENT_SQLITE_PATH"]))
    run = RunResponse(
        id="test-run-002",
        status="completed",
        skill_id="product-analysis",
        question="No manifest",
        artifacts=[
            Artifact(type=ArtifactType.markdown_report, title="MD Report", content="# MD"),
        ],
    )
    store.record_run(run)
    response = test_client.get("/api/runs/test-run-002/export")
    assert response.status_code == 400


def test_export_with_missing_manifest_snapshot_keys_returns_400(test_client, tmp_path):
    """GET /api/runs/{run_id}/export returns 400 when visual_report is missing manifest/snapshot keys."""
    import os
    from app.memory.store import MemoryStore
    from app.models.schemas import RunResponse, Artifact, ArtifactType

    db_path = tmp_path / "test.db"
    store = MemoryStore(db_path)
    run = RunResponse(
        id="test-run-003",
        status="completed",
        skill_id="test",
        question="test",
        project_id="proj",
        artifacts=[
            Artifact(type=ArtifactType.visual_report, title="图文分析报告", data={"snapshot": {}}),
        ],
    )
    store.record_run(run)

    resp = test_client.get("/api/runs/test-run-003/export")
    assert resp.status_code == 400
    assert "missing manifest/snapshot" in resp.json()["detail"]


def test_import_validate_valid_package(test_client):
    """POST /api/runs/import-validate with a valid exported package."""
    # First export to get a valid package
    export_resp = test_client.get("/api/runs/test-run-001/export")
    assert export_resp.status_code == 200
    package_data = export_resp.json()

    # Upload it for validation
    package_bytes = json.dumps(package_data).encode("utf-8")
    files = {"file": ("test-package.json", io.BytesIO(package_bytes), "application/json")}
    resp = test_client.post("/api/runs/import-validate", files=files)
    assert resp.status_code == 200
    result = resp.json()
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["filename"] == "test-package.json"


def test_import_validate_corrupted_checksum(test_client):
    """POST /api/runs/import-validate detects checksum corruption."""
    export_resp = test_client.get("/api/runs/test-run-001/export")
    assert export_resp.status_code == 200
    package_data = export_resp.json()

    # Corrupt the manifest
    package_data["manifest"]["title"] = "CORRUPTED"
    package_bytes = json.dumps(package_data).encode("utf-8")
    files = {"file": ("corrupted.json", io.BytesIO(package_bytes), "application/json")}
    resp = test_client.post("/api/runs/import-validate", files=files)
    assert resp.status_code == 200
    result = resp.json()
    assert result["valid"] is False
    assert any("checksum" in e.lower() for e in result["errors"])


def test_import_validate_invalid_json(test_client):
    """POST /api/runs/import-validate returns 200 with valid=false for invalid JSON."""
    files = {"file": ("bad.json", io.BytesIO(b"not json"), "application/json")}
    resp = test_client.post("/api/runs/import-validate", files=files)
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert any("Invalid JSON" in e for e in resp.json()["errors"])


def test_import_validate_non_json_file(test_client):
    """POST /api/runs/import-validate rejects non-JSON filename."""
    files = {"file": ("data.txt", io.BytesIO(b"{}"), "text/plain")}
    resp = test_client.post("/api/runs/import-validate", files=files)
    assert resp.status_code == 400
    assert "JSON" in resp.json()["detail"]


def test_import_validate_missing_required_fields(test_client):
    """POST /api/runs/import-validate detects missing required fields."""
    incomplete = {"manifest": {"title": "incomplete"}}
    files = {"file": ("incomplete.json", io.BytesIO(json.dumps(incomplete).encode()), "application/json")}
    resp = test_client.post("/api/runs/import-validate", files=files)
    assert resp.status_code == 200
    result = resp.json()
    assert result["valid"] is False
    assert any("Missing required field" in e for e in result["errors"])
