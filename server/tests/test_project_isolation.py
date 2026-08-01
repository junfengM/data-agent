"""Regression tests: project-scoped isolation for semantic layers,
source routing, onboarding progress, datasets, and runs."""
import pytest
from pathlib import Path
from uuid import uuid4

from app.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return MemoryStore(db_path)


class TestSemanticLayerIsolation:
    def test_list_semantic_layers_none_project_returns_empty(self, store):
        """No-project query must not return any semantic layers."""
        layers = store.list_semantic_layers(None)
        assert layers == []

    def test_list_semantic_layers_empty_string_returns_empty(self, store):
        """Empty-string project_id must not return any semantic layers."""
        layers = store.list_semantic_layers("")
        assert layers == []

    def test_project_layers_are_isolated(self, store):
        """Two projects see only their own semantic layers."""
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        store.create_semantic_layer({
            "project_id": pid_a, "name": "Project A Metrics", "path": "/tmp/a.yaml",
        })
        store.create_semantic_layer({
            "project_id": pid_b, "name": "Project B Metrics", "path": "/tmp/b.yaml",
        })

        layers_a = store.list_semantic_layers(pid_a)
        layers_b = store.list_semantic_layers(pid_b)

        assert len(layers_a) == 1
        assert layers_a[0]["name"] == "Project A Metrics"
        assert len(layers_b) == 1
        assert layers_b[0]["name"] == "Project B Metrics"


class TestSourceRoutingIsolation:
    def test_get_source_routing_none_project_returns_empty(self, store):
        """No-project query must not return any source routing."""
        routing = store.get_source_routing(None)
        assert routing == {}

    def test_get_source_routing_empty_string_returns_empty(self, store):
        routing = store.get_source_routing("")
        assert routing == {}

    def test_two_projects_keep_independent_routing(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        store.update_source_routing(pid_a, {"structured_data": "prefer"})
        store.update_source_routing(pid_b, {"structured_data": "avoid"})

        routing_a = store.get_source_routing(pid_a)
        routing_b = store.get_source_routing(pid_b)

        assert routing_a["structured_data"] == "prefer"
        assert routing_b["structured_data"] == "avoid"

    def test_get_source_routing_only_returns_target_project(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        store.update_source_routing(pid_a, {"product_analytics": "prefer"})
        store.update_source_routing(pid_b, {"company_docs": "neutral"})

        routing_a = store.get_source_routing(pid_a)
        assert routing_a == {"product_analytics": "prefer"}
        assert "company_docs" not in routing_a


class TestOnboardingIsolation:
    def test_get_onboarding_progress_none_project_returns_default(self, store):
        progress = store.get_onboarding_progress(None)
        assert progress == {"step": "welcome", "completed_steps": []}

    def test_get_onboarding_progress_empty_string_returns_default(self, store):
        progress = store.get_onboarding_progress("")
        assert progress == {"step": "welcome", "completed_steps": []}


class TestSemanticLayerOrdering:
    def test_layers_ordered_by_created_at_desc(self, store):
        pid = uuid4().hex
        store.create_semantic_layer({
            "project_id": pid, "name": "First", "path": "/tmp/a.yaml",
        })
        store.create_semantic_layer({
            "project_id": pid, "name": "Second", "path": "/tmp/b.yaml",
        })
        layers = store.list_semantic_layers(pid)
        assert len(layers) == 2
        assert layers[0]["name"] == "Second"  # most recent first

    def test_first_layer_is_latest(self, store):
        pid = uuid4().hex
        store.create_semantic_layer({
            "project_id": pid, "name": "Older", "path": "/tmp/old.yaml",
        })
        import time
        time.sleep(0.01)
        store.create_semantic_layer({
            "project_id": pid, "name": "Newer", "path": "/tmp/new.yaml",
        })
        layers = store.list_semantic_layers(pid)
        assert layers[0]["name"] == "Newer"


class TestDatasetProjectIsolation:
    def test_record_dataset_with_project_id(self, store):
        pid = uuid4().hex
        ds_id = store.record_dataset(
            path=Path("/tmp/test.csv"),
            filename="test.csv",
            content_type="text/csv",
            project_id=pid,
        )
        ds = store.get_dataset(ds_id)
        assert ds is not None
        assert ds.project_id == pid

    def test_list_datasets_filters_by_project(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        store.record_dataset(Path("/tmp/a.csv"), "a.csv", "text/csv", project_id=pid_a)
        store.record_dataset(Path("/tmp/b.csv"), "b.csv", "text/csv", project_id=pid_b)
        store.record_dataset(Path("/tmp/global.csv"), "global.csv", "text/csv", project_id=None)

        datasets_a = store.list_datasets(project_id=pid_a)
        datasets_b = store.list_datasets(project_id=pid_b)

        # pid_a sees its own + global datasets, but not pid_b's
        filenames_a = {d.filename for d in datasets_a}
        assert "a.csv" in filenames_a
        assert "global.csv" in filenames_a
        assert "b.csv" not in filenames_a

        filenames_b = {d.filename for d in datasets_b}
        assert "b.csv" in filenames_b
        assert "global.csv" in filenames_b
        assert "a.csv" not in filenames_b

    def test_get_dataset_with_project_validation_allows_own_dataset(self, store):
        pid = uuid4().hex
        ds_id = store.record_dataset(Path("/tmp/x.csv"), "x.csv", "text/csv", project_id=pid)

        ds = store.get_dataset(ds_id, project_id=pid)
        assert ds is not None
        assert ds.filename == "x.csv"

    def test_get_dataset_with_project_validation_allows_global_dataset(self, store):
        ds_id = store.record_dataset(Path("/tmp/g.csv"), "g.csv", "text/csv", project_id=None)

        ds = store.get_dataset(ds_id, project_id=uuid4().hex)
        assert ds is not None
        assert ds.filename == "g.csv"

    def test_legacy_dataset_without_project_id_still_works(self, store):
        # Simulate legacy data: insert row without project_id
        ds_id = uuid4().hex
        with store._connect() as conn:
            conn.execute(
                "insert into datasets (id, filename, path, content_type) values (?, ?, ?, ?)",
                (ds_id, "legacy.csv", "/tmp/legacy.csv", "text/csv"),
            )

        ds = store.get_dataset(ds_id)
        assert ds is not None
        assert ds.filename == "legacy.csv"
        assert ds.project_id is None


class TestRunProjectIsolation:
    def test_get_run_with_wrong_project_returns_none(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex
        from app.models.schemas import RunResponse

        run = RunResponse(
            status="completed",
            skill_id="explore",
            question="test",
            project_id=pid_a,
        )
        store.record_run(run)

        found = store.get_run(run.id, project_id=pid_a)
        assert found is not None

        not_found = store.get_run(run.id, project_id=pid_b)
        assert not_found is None

    def test_list_runs_filters_by_project_id(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex
        from app.models.schemas import RunResponse

        run_a = RunResponse(status="completed", skill_id="explore", question="A", project_id=pid_a)
        run_b = RunResponse(status="completed", skill_id="explore", question="B", project_id=pid_b)
        store.record_run(run_a)
        store.record_run(run_b)

        runs_a = store.list_runs(project_id=pid_a)
        assert len(runs_a) == 1
        assert runs_a[0].question == "A"

        runs_b = store.list_runs(project_id=pid_b)
        assert len(runs_b) == 1
        assert runs_b[0].question == "B"
