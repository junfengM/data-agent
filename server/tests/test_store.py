import pytest
from uuid import uuid4

from app.memory.store import MemoryStore
from app.models.schemas import Artifact, ArtifactType, RunResponse, ToolCall, ValidationResultModel


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return MemoryStore(db_path)


def make_run(
    run_id: str,
    project_id: str | None = None,
    status: str = "completed",
    skill_id: str = "explore",
    question: str = "test question",
    artifacts: list[Artifact] | None = None,
    tool_calls: list[ToolCall] | None = None,
) -> RunResponse:
    return RunResponse(
        id=run_id,
        status=status,
        skill_id=skill_id,
        question=question,
        project_id=project_id,
        artifacts=artifacts or [],
        tool_calls=tool_calls or [],
    )


class TestRunPersistence:
    def test_get_run_returns_none_for_missing(self, store):
        assert store.get_run("nonexistent") is None

    def test_record_then_get_run_roundtrip(self, store):
        run = make_run(
            run_id=uuid4().hex,
            project_id=uuid4().hex,
            status="completed",
            skill_id="explore",
            question="what is the average sales?",
            artifacts=[
                Artifact(
                    type=ArtifactType.chart,
                    title="Sales Chart",
                    content='{"chart": {"type": "bar"}}',
                ),
                Artifact(
                    type=ArtifactType.markdown_report,
                    title="Summary Report",
                    content="# Sales Report\n\nAverage sales: 1234",
                ),
            ],
            tool_calls=[
                ToolCall(
                    name="load_data",
                    input_summary="Load sales.csv",
                    output_summary="Loaded 100 rows",
                    status="completed",
                ),
                ToolCall(
                    name="run_python",
                    input_summary="Calculate average sales",
                    output_summary="avg=1234",
                    status="completed",
                ),
            ],
        )

        store.record_run(run)
        retrieved = store.get_run(run.id)

        assert retrieved is not None
        assert retrieved.id == run.id
        assert retrieved.status == run.status
        assert retrieved.skill_id == run.skill_id
        assert retrieved.question == run.question
        assert retrieved.project_id == run.project_id

        assert len(retrieved.artifacts) == 2
        assert retrieved.artifacts[0].title == "Sales Chart"
        assert retrieved.artifacts[0].type == ArtifactType.chart
        assert retrieved.artifacts[1].title == "Summary Report"
        assert retrieved.artifacts[1].type == ArtifactType.markdown_report

        assert len(retrieved.tool_calls) == 2
        assert retrieved.tool_calls[0].name == "load_data"
        assert retrieved.tool_calls[0].status == "completed"
        assert retrieved.tool_calls[1].name == "run_python"

    def test_list_runs_with_project_filter(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        run_a1 = make_run(run_id=uuid4().hex, project_id=pid_a, question="A1")
        run_a2 = make_run(run_id=uuid4().hex, project_id=pid_a, question="A2")
        run_b1 = make_run(run_id=uuid4().hex, project_id=pid_b, question="B1")

        store.record_run(run_a1)
        store.record_run(run_a2)
        store.record_run(run_b1)

        runs_a = store.list_runs(project_id=pid_a)
        runs_b = store.list_runs(project_id=pid_b)

        assert len(runs_a) == 2
        assert {r.id for r in runs_a} == {run_a1.id, run_a2.id}
        assert len(runs_b) == 1
        assert runs_b[0].id == run_b1.id

    def test_list_runs_without_project_filter(self, store):
        pid = uuid4().hex
        run1 = make_run(run_id=uuid4().hex, project_id=pid, question="Q1")
        run2 = make_run(run_id=uuid4().hex, project_id=pid, question="Q2")

        store.record_run(run1)
        store.record_run(run2)

        all_runs = store.list_runs()
        assert len(all_runs) == 2
        assert {r.id for r in all_runs} == {run1.id, run2.id}

    def test_list_runs_none_project_returns_all(self, store):
        pid_a = uuid4().hex
        pid_b = uuid4().hex

        store.record_run(make_run(run_id=uuid4().hex, project_id=pid_a, question="A"))
        store.record_run(make_run(run_id=uuid4().hex, project_id=pid_b, question="B"))

        all_runs = store.list_runs(project_id=None)
        assert len(all_runs) == 2

    def test_list_runs_empty_when_no_runs(self, store):
        assert store.list_runs() == []
        assert store.list_runs(project_id="nonexistent") == []

    def test_run_events_persist_in_order(self, store):
        run_id = uuid4().hex
        store.record_run(make_run(run_id=run_id, status="running"))

        first = store.record_run_event(
            run_id,
            event_type="llm_request_started",
            summary="Calling model",
            data={"iteration": 1, "prompt_chars": 1200},
            elapsed_ms=25,
        )
        second = store.record_run_event(
            run_id,
            event_type="tool_completed",
            summary="Analysis step completed",
            data={"tool": "execute_code", "returncode": 0},
            elapsed_ms=240,
        )

        events = store.list_run_events(run_id)
        assert [event["sequence"] for event in events] == [first, second]
        assert events[0]["type"] == "llm_request_started"
        assert events[0]["elapsed_ms"] == 25
        assert events[1]["data"]["returncode"] == 0


class TestValidationContract:
    def test_run_response_includes_validation_results(self, store):
        vr = [
            ValidationResultModel(
                gate_id="evidence_coverage",
                passed=True,
                message="Found 3 tables",
                severity="pass",
                details={"tables": 3, "charts": 2},
            ),
            ValidationResultModel(
                gate_id="source_metadata",
                passed=False,
                message="Missing source metadata",
                severity="warning",
            ),
        ]
        run = make_run(
            run_id=uuid4().hex,
            status="completed",
            question="test validation",
        )
        run.validation_results = vr
        run.validation_passed = False

        store.record_run(run)
        retrieved = store.get_run(run.id)

        assert retrieved is not None
        assert len(retrieved.validation_results) == 2
        assert retrieved.validation_results[0].gate_id == "evidence_coverage"
        assert retrieved.validation_results[0].passed is True
        assert retrieved.validation_results[0].severity == "pass"
        assert retrieved.validation_results[1].gate_id == "source_metadata"
        assert retrieved.validation_results[1].passed is False
        assert retrieved.validation_passed is False

    def test_run_response_backward_compatible_without_validation_fields(self):
        payload = {
            "id": uuid4().hex,
            "status": "completed",
            "skill_id": "explore",
            "question": "old run without validation",
            "artifacts": [],
            "tool_calls": [],
            "workflow_steps": [],
        }
        run = RunResponse.model_validate(payload)
        assert run.validation_results == []
        assert run.validation_passed is None

    def test_run_response_serializes_validation_fields(self):
        run = make_run(run_id=uuid4().hex, status="completed", question="test")
        run.validation_results = [
            ValidationResultModel(
                gate_id="metric_completeness",
                passed=True,
                message="All metrics defined",
                severity="pass",
            )
        ]
        run.validation_passed = True

        data = run.model_dump(mode="json")
        assert "validation_results" in data
        assert len(data["validation_results"]) == 1
        assert data["validation_results"][0]["gate_id"] == "metric_completeness"
        assert data["validation_passed"] is True
