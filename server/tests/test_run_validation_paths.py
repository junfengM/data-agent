from pathlib import Path

from app.agent.run_validation import run_and_apply_validation
from app.models.schemas import Artifact, ArtifactManifest, ArtifactType, RunResponse


class _SemanticLayer:
    metrics = []
    dimensions = []


class _Preflight:
    context_gaps = []


def test_postrun_file_validation_uses_run_artifacts_dir(tmp_path: Path):
    run_id = "run_temp_workspace"
    artifacts_dir = tmp_path / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "chart.html").write_text("<div>chart</div>", encoding="utf-8")
    (artifacts_dir / "web_report.html").write_text(
        '<iframe src="/api/runs/run_temp_workspace/assets/chart.html"></iframe>',
        encoding="utf-8",
    )

    run = RunResponse(id=run_id, status="running", skill_id="auto", question="demo")
    run.artifacts = [
        Artifact(
            type=ArtifactType.chart,
            title="Chart",
            data={"render_mode": "file", "path": "chart.html", "chart_type": "html"},
        ),
        Artifact(
            type=ArtifactType.html_report,
            title="Web Report",
            path=Path("web_report.html"),
        ),
    ]

    _passed, _fail, _warn, results = run_and_apply_validation(
        run=run,
        manifest=ArtifactManifest(title="Demo"),
        step_results=[],
        report_md="Demo report",
        plan_caveats=[],
        profiles=[],
        semantic_layer=_SemanticLayer(),
        preflight=_Preflight(),
        project_contexts=None,
        artifacts_dir=artifacts_dir,
    )

    file_gate = next(r for r in results if r.gate_id == "file_chart_asset_refs")
    web_gate = next(r for r in results if r.gate_id == "web_report_chart_embeds")

    assert file_gate.passed, file_gate.message
    assert web_gate.passed, web_gate.message
