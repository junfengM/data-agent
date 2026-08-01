"""Visual report assembly pipeline (extracted from orchestrator.py).

Pure function: takes plain values, calls build_artifact_manifest →
build_visual_deck_blocks → audit_visual_coverage →
attach_stable_source_ids → dedupe_appendix_visual_evidence →
compose_reading_flow, and returns (manifest, snapshot).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.artifact_manifest import build_artifact_manifest
from app.agent.artifact_manifest_semantics import detect_semantic_conflicts
from app.agent.visual_adaptation import load_visual_recipes
from app.agent.visual_deck_blocks import audit_visual_coverage, build_visual_deck_blocks
from app.agent.visual_deck_evidence import (
    attach_stable_source_ids,
    dedupe_appendix_visual_evidence,
)
from app.agent.visual_report_planner import compose_reading_flow
from app.models.schemas import (
    ArtifactBlockType,
    ArtifactManifest,
    ArtifactSnapshot,
    CandidateAngle,
    DatasetProfile,
    ProjectContext,
)


def assemble_visual_report(
    title: str,
    report_md: str,
    step_results: list[dict],
    profiles: list[DatasetProfile],
    project_contexts: list[ProjectContext] | None,
    candidate_angles: list[CandidateAngle],
    chart_specs: list[dict],
    plan_caveats: list[str] | None,
    semantic_layer: dict | None,
    semantic_layer_path: str | None,
    visual_plan: list[dict[str, Any]],
    workspace_dir: Path,
    project_id: str | None,
) -> tuple[ArtifactManifest, ArtifactSnapshot]:
    sl_data: dict | None = None
    if semantic_layer:
        sl_data = {
            "metrics": semantic_layer.metrics,
            "dimensions": semantic_layer.dimensions,
            "caveats": semantic_layer.caveats,
            "path": str(semantic_layer_path) if semantic_layer_path else None,
        }
        conflicts, ambiguities = detect_semantic_conflicts(sl_data)
        sl_data["conflicts"] = conflicts
        sl_data["ambiguities"] = ambiguities

    manifest, snapshot = build_artifact_manifest(
        title=title,
        report_md=report_md,
        step_results=step_results,
        profiles=profiles,
        project_contexts=project_contexts,
        candidate_angles=candidate_angles,
        chart_specs=chart_specs,
        plan_caveats=plan_caveats,
        semantic_layer=sl_data,
        visual_plan=visual_plan,
        visual_recipes=load_visual_recipes(workspace_dir, project_id),
    )

    deck_blocks = build_visual_deck_blocks(
        title=title,
        report_md=report_md,
        manifest=manifest,
        snapshot=snapshot,
        plan_caveats=plan_caveats,
        visual_plan=list(getattr(manifest, "visual_plan", []) or []),
        visual_recipes=list(getattr(manifest, "visual_recipes", []) or []),
    )
    coverage, proposals = audit_visual_coverage(report_md, deck_blocks)
    manifest.visual_coverage = coverage
    manifest.visual_iteration = proposals
    attach_stable_source_ids(manifest, snapshot)
    dedupe_appendix_visual_evidence(manifest)

    existing_blocks = list(getattr(manifest, "blocks", []) or [])
    narrative_blocks = [b for b in existing_blocks if b.type == ArtifactBlockType.markdown]
    evidence_blocks = [b for b in existing_blocks if b.renderer_target == "evidence_component"]
    appendix_blocks = [b for b in existing_blocks if b.renderer_target == "appendix"]
    manifest_md_visual = [b for b in existing_blocks if b.renderer_target == "md_visual"]
    manifest.blocks = compose_reading_flow(
        narrative_blocks=narrative_blocks,
        md_visual_blocks=deck_blocks + manifest_md_visual,
        evidence_component_blocks=evidence_blocks,
        appendix_blocks=appendix_blocks,
    )

    return manifest, snapshot
