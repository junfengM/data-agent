import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client(tmp_path: Path):
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
    from app.models.schemas import AnalysisProjectCreate

    store = MemoryStore(db_path)
    project = store.create_project(AnalysisProjectCreate(name="Test Project"))

    # Create a semantic layer YAML file so load_semantic_layer won't fail
    layer_path = tmp_path / "test-layer.yaml"
    layer_path.write_text(
        json.dumps({
            "metrics": [
                {
                    "name": "revenue",
                    "formula": "SUM(revenue)",
                    "grain": "monthly",
                    "dimensions": ["category"],
                    "sources": ["sales.csv"],
                    "caveat": "Excludes refunds",
                }
            ],
            "dimensions": [
                {"name": "category", "source_column": "product_category"}
            ],
            "caveats": [
                {"description": "Data incomplete before Q1 2024"}
            ],
        }),
        encoding="utf-8",
    )

    layer2_path = tmp_path / "test-layer-v2.yaml"
    layer2_path.write_text(
        json.dumps({
            "metrics": [
                {
                    "name": "orders",
                    "formula": "COUNT(orders)",
                    "grain": "daily",
                    "dimensions": ["region"],
                    "sources": ["orders.csv"],
                    "caveat": "Excludes cancelled",
                }
            ],
            "dimensions": [],
            "caveats": [],
        }),
        encoding="utf-8",
    )

    # Create two semantic layers via store directly
    layer1 = store.create_semantic_layer({
        "project_id": project.id,
        "name": "v1",
        "path": str(layer_path),
    })
    layer2 = store.create_semantic_layer({
        "project_id": project.id,
        "name": "v2",
        "path": str(layer2_path),
    })

    yield {
        "client": TestClient(app),
        "project_id": project.id,
        "layer1_id": layer1["id"],
        "layer2_id": layer2["id"],
    }

    for key in (
        "DATA_AGENT_WORKSPACE_DIR",
        "DATA_AGENT_SQLITE_PATH",
        "DATA_AGENT_GENERATED_CODE_EXECUTION",
    ):
        os.environ.pop(key, None)


# ── Active layer tests ──────────────────────────────────────────────────

def test_active_layer_missing_project_returns_404(test_client):
    response = test_client["client"].get(
        "/api/projects/nonexistent/semantic-layers/active"
    )
    assert response.status_code == 404


def test_active_layer_returns_metadata(test_client):
    response = test_client["client"].get(
        f"/api/projects/{test_client['project_id']}/semantic-layers/active"
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert "path" in data
    assert "is_active" in data
    assert "metrics" in data
    assert "dimensions" in data
    assert "caveats" in data
    assert data["name"] == "v2"  # latest by created_at when no is_active set


# ── Inspect layer tests ─────────────────────────────────────────────────

def test_inspect_layer_missing_project_returns_404(test_client):
    response = test_client["client"].get(
        "/api/projects/nonexistent/semantic-layers/some-id"
    )
    assert response.status_code == 404


def test_inspect_layer_missing_layer_returns_404(test_client):
    response = test_client["client"].get(
        f"/api/projects/{test_client['project_id']}/semantic-layers/nonexistent"
    )
    assert response.status_code == 404


def test_inspect_layer_valid_returns_content(test_client):
    response = test_client["client"].get(
        f"/api/projects/{test_client['project_id']}"
        f"/semantic-layers/{test_client['layer1_id']}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_client["layer1_id"]
    assert "name" in data
    assert "metrics" in data
    assert "dimensions" in data
    assert "caveats" in data


# ── List layers tests ───────────────────────────────────────────────────

def test_list_layers_missing_project_returns_404(test_client):
    response = test_client["client"].get(
        "/api/projects/nonexistent/semantic-layers"
    )
    assert response.status_code == 404


def test_list_layers_returns_all(test_client):
    response = test_client["client"].get(
        f"/api/projects/{test_client['project_id']}/semantic-layers"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    ids = {layer["id"] for layer in data}
    assert test_client["layer1_id"] in ids
    assert test_client["layer2_id"] in ids


# ── Create layer tests ──────────────────────────────────────────────────

def test_create_layer_missing_project_returns_404(test_client):
    response = test_client["client"].post(
        "/api/projects/nonexistent/semantic-layers",
        json={"name": "test", "path": "/tmp/test.yaml"},
    )
    assert response.status_code == 404


def test_create_layer_returns_new_layer(test_client):
    # Create YAML inside the project workspace directory to satisfy path safety
    project_dir = Path(os.environ["DATA_AGENT_WORKSPACE_DIR"]) / "projects" / test_client["project_id"]
    project_dir.mkdir(parents=True, exist_ok=True)
    new_path = str(project_dir / "new-layer.yaml")
    Path(new_path).write_text(
        json.dumps({"metrics": [], "dimensions": [], "caveats": []}),
        encoding="utf-8",
    )
    response = test_client["client"].post(
        f"/api/projects/{test_client['project_id']}/semantic-layers",
        json={"name": "new-layer", "path": new_path},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "new-layer"
    assert data["path"] == new_path
    assert "id" in data


# ── Promote layer tests ─────────────────────────────────────────────────

def test_promote_layer_missing_layer_returns_404(test_client):
    response = test_client["client"].post(
        f"/api/projects/{test_client['project_id']}"
        f"/semantic-layers/nonexistent/promote"
    )
    assert response.status_code == 404


def test_promote_then_active_returns_promoted(test_client):
    # Promote older layer (layer1)
    promote_response = test_client["client"].post(
        f"/api/projects/{test_client['project_id']}"
        f"/semantic-layers/{test_client['layer1_id']}/promote"
    )
    assert promote_response.status_code == 200
    assert promote_response.json()["status"] == "ok"

    # Active should now return layer1 (promoted), not layer2 (latest by date)
    active_response = test_client["client"].get(
        f"/api/projects/{test_client['project_id']}/semantic-layers/active"
    )
    assert active_response.status_code == 200
    data = active_response.json()
    assert data["id"] == test_client["layer1_id"]
    assert data["is_active"] is True
    assert data["name"] == "v1"


# ── Confirm draft tests ──────────────────────────────────────────────────


@pytest.fixture
def draft_client(tmp_path: Path):
    """Fixture with a project, dataset, and semantic draft ready for confirm tests."""
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
    from app.models.schemas import AnalysisProjectCreate

    store = MemoryStore(db_path)
    project = store.create_project(AnalysisProjectCreate(name="Test Project"))

    # Create a small CSV file
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("id,amount,date\n1,100,2024-01-01\n2,200,2024-01-02\n", encoding="utf-8")

    dataset_id = store.record_dataset(csv_path, "test.csv", "text/csv", project_id=project.id)

    client = TestClient(app)

    # Create semantic draft (heuristic only, no LLM)
    draft_response = client.post(
        f"/api/projects/{project.id}/datasets/{dataset_id}/semantic-draft",
        json={"use_llm": False},
    )
    assert draft_response.status_code == 200, f"Draft creation failed: {draft_response.text}"
    draft = draft_response.json()

    yield {
        "client": client,
        "project_id": project.id,
        "dataset_id": dataset_id,
        "draft_id": draft["id"],
        "workspace": workspace,
    }

    for key in (
        "DATA_AGENT_WORKSPACE_DIR",
        "DATA_AGENT_SQLITE_PATH",
        "DATA_AGENT_GENERATED_CODE_EXECUTION",
    ):
        os.environ.pop(key, None)


def test_confirm_dry_run_returns_preview(draft_client):
    """confirm?dry_run=true returns preview without writing."""
    response = draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm?dry_run=true"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "preview"
    assert "can_confirm" in data
    assert "blockers" in data
    assert "warnings" in data
    assert "would_add" in data or "would_keep" in data or "would_replace" in data


def test_confirm_dry_run_does_not_write_yaml(draft_client):
    """dry_run does not create a semantic-layer.yaml file."""
    draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm?dry_run=true"
    )
    layer_path = (
        Path(os.environ["DATA_AGENT_WORKSPACE_DIR"])
        / "projects"
        / draft_client["project_id"]
        / "semantic-layer.yaml"
    )
    assert not layer_path.exists()


def test_confirm_warning_case_succeeds(draft_client):
    """Warning-only case can confirm and returns warnings."""
    response = draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm"
    )
    # Should succeed — heuristic draft from clean CSV has no blockers
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
    assert "metrics_written" in data


def test_confirm_writes_semantic_layer_yaml(draft_client):
    """Successful confirm creates semantic-layer.yaml."""
    draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm"
    )
    layer_path = (
        Path(os.environ["DATA_AGENT_WORKSPACE_DIR"])
        / "projects"
        / draft_client["project_id"]
        / "semantic-layer.yaml"
    )
    assert layer_path.exists()
    content = layer_path.read_text(encoding="utf-8")
    assert "metrics" in content.lower() or "dimensions" in content.lower()


def test_confirm_provenance_draft_id_preserved(draft_client):
    """Confirmed metric retains provenance.draft_id — guaranteed metric."""
    import yaml
    response = draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm"
    )
    assert response.status_code == 200

    layer_path = (
        Path(os.environ["DATA_AGENT_WORKSPACE_DIR"])
        / "projects"
        / draft_client["project_id"]
        / "semantic-layer.yaml"
    )
    layer = yaml.safe_load(layer_path.read_text(encoding="utf-8"))
    metrics = layer.get("metrics", [])
    assert len(metrics) > 0, "Expected at least one metric in confirmed layer"

    provenanced = [m for m in metrics if "provenance" in m]
    assert len(provenanced) > 0, "Expected at least one metric with provenance"

    for m in provenanced:
        assert m["provenance"]["draft_id"] == draft_client["draft_id"], (
            f"provenance.draft_id {m['provenance']['draft_id']} != {draft_client['draft_id']}"
        )


def test_confirm_409_on_blocker_yaml_unchanged(draft_client):
    """Construct guaranteed blocker via PATCH — confirm returns 409, YAML unchanged."""
    import yaml
    from app.memory.store import MemoryStore

    workspace = Path(os.environ["DATA_AGENT_WORKSPACE_DIR"])
    projects_dir = workspace / "projects" / draft_client["project_id"]

    # Step 1: confirm first draft to write baseline YAML
    draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft_client['draft_id']}/confirm"
    )

    layer_path = projects_dir / "semantic-layer.yaml"
    assert layer_path.exists()
    original_yaml = layer_path.read_text(encoding="utf-8")
    original_layer = yaml.safe_load(original_yaml)
    assert len(original_layer.get("metrics", [])) > 0, "Baseline layer must have metrics"

    # Step 2: create second dataset with same column name but different semantics
    store = MemoryStore(Path(os.environ["DATA_AGENT_SQLITE_PATH"]))
    csv2 = workspace / "blocker_test.csv"
    csv2.write_text("id,amount\n1,50\n2,60\n", encoding="utf-8")
    ds2_id = store.record_dataset(csv2, "blocker_test.csv", "text/csv", project_id=draft_client["project_id"])

    draft2_resp = draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}/datasets/{ds2_id}/semantic-draft",
        json={"use_llm": False},
    )
    assert draft2_resp.status_code == 200
    draft2 = draft2_resp.json()

    # Step 3: PATCH second draft to change amount's aggregation to AVG,
    # creating formula conflict with existing SUM(amount)
    patch_resp = draft_client["client"].patch(
        f"/api/projects/{draft_client['project_id']}/semantic-drafts/{draft2['id']}",
        json={
            "columns": [
                {
                    "source_column": "amount",
                    "role": "metric",
                    "default_aggregation": "avg",
                    "semantic_type": "currency_amount",
                    "grain": "row",
                    "confidence": 0.9,
                    "include_in_layer": True,
                },
                {
                    "source_column": "id",
                    "role": "identifier",
                    "default_aggregation": "count_distinct",
                    "semantic_type": "entity_id",
                    "grain": "row",
                    "confidence": 0.9,
                    "include_in_layer": True,
                },
            ],
        },
    )
    assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"

    # Step 4: confirm second draft — must return 409
    confirm_resp = draft_client["client"].post(
        f"/api/projects/{draft_client['project_id']}"
        f"/semantic-drafts/{draft2['id']}/confirm"
    )

    assert confirm_resp.status_code == 409, (
        f"Expected 409 blocker, got {confirm_resp.status_code}: {confirm_resp.text}"
    )
    detail = confirm_resp.json()["detail"]
    assert "semantic_merge_blocked" in str(detail)
    assert "blockers" in str(detail) or detail.get("blockers")

    # Step 5: verify YAML unchanged
    current_yaml = layer_path.read_text(encoding="utf-8")
    assert current_yaml == original_yaml, "semantic-layer.yaml was modified despite 409"
