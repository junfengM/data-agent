"""Regression tests for top-level run status finalization (DA-OPT-002).

Unexpected exceptions or task cancellation must never leave a run stuck in
``running`` inside the SQLite store.
"""
import asyncio
from pathlib import Path

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.planner import Planner
from app.memory.store import MemoryStore
from app.models.schemas import AnalysisRequest, ArtifactType

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def orch(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "index.md").write_text("# Index\n", encoding="utf-8")

    store = MemoryStore(tmp_path / "test.db")
    return AgentOrchestrator(
        skills_dir=skills_dir,
        workspace_dir=tmp_path / "workspace",
        config_dir=REPO_ROOT / "config",
        store=store,
        generated_code_execution="disabled",
    )


def _request() -> AnalysisRequest:
    return AnalysisRequest(question="test question")


@pytest.mark.anyio
async def test_unexpected_pipeline_error_persists_failed_status(orch, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("profile boom")

    monkeypatch.setattr("app.agent.orchestrator.profile_datasets", boom)

    with pytest.raises(RuntimeError, match="profile boom"):
        await orch.run(_request())

    stored = orch.store.list_runs()
    assert len(stored) == 1
    assert stored[0].status == "failed"
    assert any(call.name == "run_error" for call in stored[0].tool_calls)


@pytest.mark.anyio
async def test_cancelled_run_persists_cancelled_status(orch, monkeypatch):
    def cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.agent.orchestrator.profile_datasets", cancel)

    with pytest.raises(asyncio.CancelledError):
        await orch.run(_request())

    stored = orch.store.list_runs()
    assert len(stored) == 1
    assert stored[0].status == "cancelled"


@pytest.mark.anyio
async def test_planner_model_failure_without_evidence_marks_run_failed(orch, monkeypatch):
    def mock_init(self, model_config):
        self.config = model_config
        self.index_content = ""

    async def auth_fail(self, **kwargs):
        raise RuntimeError("AuthenticationError: invalid api key")

    monkeypatch.setattr(Planner, "__init__", mock_init)
    monkeypatch.setattr(Planner, "run_analysis", auth_fail)

    run = await orch.run(_request())

    assert run.status == "failed"
    assert not any(a.type == ArtifactType.markdown_report for a in run.artifacts)
    assert any(a.type == ArtifactType.run_log for a in run.artifacts)
    assert any(
        tc.name == "llm_planner" and tc.status == "failed" for tc in run.tool_calls
    )
    stored = orch.store.get_run(run.id)
    assert stored is not None
    assert stored.status == "failed"


@pytest.mark.anyio
async def test_planner_failure_with_evidence_keeps_fallback(orch, monkeypatch):
    def mock_init(self, model_config):
        self.config = model_config
        self.index_content = ""

    async def fail_after_step(self, code_executor=None, **kwargs):
        if code_executor:
            await code_executor("print('x')", "step_1", "compute")
        raise RuntimeError("planner crashed after executing step")

    monkeypatch.setattr(Planner, "__init__", mock_init)
    monkeypatch.setattr(Planner, "run_analysis", fail_after_step)

    run = await orch.run(_request())

    report = next(
        (a for a in run.artifacts if a.type == ArtifactType.markdown_report), None
    )
    assert report is not None
    assert "# 分析报告（自动恢复版）" in (report.content or "")
