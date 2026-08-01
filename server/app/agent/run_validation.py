"""Validation assembly (extracted from orchestrator.py).

Runs validation gates and writes results back to the run response and
visual_report artifact data.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from app.models.schemas import ArtifactType, RunResponse, ValidationResultModel
from app.tools.validation import run_validation_gates, validate_file_chart_asset_refs, validate_web_report_chart_embeds, validate_report_evidence_integration_postrun

_PLAN_ONLY_SKIP_GATES = frozenset({
    "evidence_coverage",
    "evidence_references",
    "source_metadata",
    "source_metadata_on_evidence",
    "visual_evidence_links",
    "chart_contracts",
    "chart_contract_compatibility",
    "chart_encoding",
    "core_conclusion_visual_support",
    "visual_report_richness",
    "table_dominance",
})


def _skip_evidence_gates_for_plan_only(validation_results: list[Any]) -> list[Any]:
    skipped: list[Any] = []
    for v in validation_results:
        if v.gate_id in _PLAN_ONLY_SKIP_GATES:
            skipped.append(replace(
                v,
                passed=True,
                severity="pass",
                message=f"{v.gate_id}: skipped in plan_only mode (no code execution)",
            ))
        else:
            skipped.append(v)
    return skipped


def run_and_apply_validation(
    run: RunResponse,
    manifest: Any,
    step_results: list[dict],
    report_md: str,
    plan_caveats: list[str] | None,
    profiles: list[Any],
    semantic_layer: Any,
    preflight: Any,
    project_contexts: list[Any] | None,
    run_mode: str = "full",
    chart_specs: list | None = None,
    artifacts_dir: Path | str | None = None,
) -> tuple[bool, int, int, list[Any]]:
    blocks_data = [b.model_dump(mode="json") for b in manifest.blocks]
    artifacts_data = [{"type": a.type.value if hasattr(a.type, "value") else a.type} for a in run.artifacts]
    semantic_layer_data = {
        "metrics": semantic_layer.metrics,
        "dimensions": semantic_layer.dimensions,
    } if semantic_layer else None

    delivery_mode = "visual_report" if run_mode != "plan_only" else "plan_only"
    validation_results = run_validation_gates(
        step_results=step_results,
        report_md=report_md,
        blocks=blocks_data,
        plan_caveats=plan_caveats,
        profiles=profiles,
        artifacts=artifacts_data,
        delivery_mode=delivery_mode,
        context_gaps=preflight.context_gaps,
        preflight_built=True,
        project_contexts=project_contexts,
        semantic_layer_data=semantic_layer_data,
        manifest_chart_ids={c.id for c in manifest.charts} if manifest.charts else None,
        manifest_table_ids={t.id for t in manifest.tables} if manifest.tables else None,
        chart_specs=chart_specs,
    )

    # File chart asset refs gate needs actual Artifact objects with paths.
    # Prefer the orchestrator's run directory because tests and local E2E
    # runs may use a workspace that differs from process-global settings.
    if artifacts_dir is not None:
        run_artifacts_dir = str(Path(artifacts_dir))
    else:
        from app.core.settings import get_settings
        ws = get_settings().resolved_workspace_dir
        run_artifacts_dir = str(ws / "artifacts" / run.id) if run.id else None
    validation_results.append(
        validate_file_chart_asset_refs(run.artifacts, artifacts_dir=run_artifacts_dir)
    )
    validation_results.append(
        validate_web_report_chart_embeds(
            run.artifacts,
            web_report_path=str(Path(run_artifacts_dir) / "web_report.html") if run_artifacts_dir else None,
        )
    )
    validation_results.append(
        validate_report_evidence_integration_postrun(
            report_md=report_md,
            step_results=step_results,
            blocks=blocks_data,
            manifest_tables=[t.model_dump(mode="json") for t in manifest.tables],
            manifest_charts=[c.model_dump(mode="json") for c in manifest.charts],
        )
    )

    if run_mode == "plan_only":
        validation_results = _skip_evidence_gates_for_plan_only(validation_results)

    validation_passed = all(v.passed for v in validation_results)
    fail_count = sum(1 for v in validation_results if v.severity == "fail" and not v.passed)
    warn_count = sum(1 for v in validation_results if v.severity == "warning" and not v.passed)

    run.validation_results = [
        ValidationResultModel(
            gate_id=v.gate_id,
            passed=v.passed,
            message=v.message,
            severity=v.severity,
            details=v.details or {},
            fix_hint=v.fix_hint,
            owner_layer=v.owner_layer,
            related_block_ids=v.related_block_ids,
            related_evidence_ids=v.related_evidence_ids,
            can_auto_repair=v.can_auto_repair,
        )
        for v in validation_results
    ]
    run.validation_passed = validation_passed

    for art in run.artifacts:
        if art.type == ArtifactType.visual_report and art.data is not None:
            art.data["validation_results"] = [v.__dict__ for v in validation_results]
            art.data["validation_passed"] = validation_passed
            break

    return validation_passed, fail_count, warn_count, validation_results
