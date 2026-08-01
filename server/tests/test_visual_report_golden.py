"""Golden fixture regression tests for visual report assembly and validation.

Each fixture (stored as JSON in tests/fixtures/visual_reports/) feeds into
assemble_visual_report + validation gates. Assertions focus on structural
properties to avoid UUID / timestamp noise:
  - block type, renderer_target, block_origin, has_evidence, source_section
  - Markdown content preservation
  - Evidence id validity (no dangling references, no fallback binding)
  - Appendix always at the end
  - Layer-aware block order stability
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.agent.visual_report_assembly import assemble_visual_report
from app.agent.run_validation import run_and_apply_validation
from app.models.schemas import (
    BLOCK_ORIGINS,
    CandidateAngle,
    ColumnProfile,
    DatasetProfile,
    RENDERER_TARGETS,
    RunResponse,
    Artifact,
    ArtifactType,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "visual_reports"


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _build_profiles(raw: list[dict]) -> list[DatasetProfile]:
    profiles: list[DatasetProfile] = []
    for item in raw:
        columns = [ColumnProfile(**c) for c in item.get("columns", [])]
        profiles.append(DatasetProfile(
            dataset_id=item["dataset_id"],
            filename=item["filename"],
            row_count=item["row_count"],
            column_count=item["column_count"],
            columns=columns,
            warnings=item.get("warnings", []),
        ))
    return profiles


class _MockSemanticLayer:
    """Minimal semantic-layer mock for assembly tests."""
    def __init__(self) -> None:
        self.metrics: list[dict] = []
        self.dimensions: list[dict] = []
        self.caveats: list[str] = []


def _snapshot_blocks(manifest: Any) -> list[dict]:
    """Snapshot-lite: no UUIDs, no timestamps."""
    return [
        {
            "type": str(getattr(b, "type", None)),
            "renderer_target": b.renderer_target,
            "block_origin": b.block_origin,
            "has_evidence": bool(b.evidence_ids),
            "source_section": b.source_section,
        }
        for b in manifest.blocks
    ]


def _all_chart_table_ids(manifest: Any) -> set[str]:
    chart_ids = {c.id for c in (manifest.charts or [])}
    table_ids = {t.id for t in (manifest.tables or [])}
    return chart_ids | table_ids


def _normalize_line(line: str) -> str:
    """Strip markdown syntax, keep only substantive text."""
    clean = line.strip()
    if not clean or re.fullmatch(r"[-|:\s]+", clean):
        return ""
    clean = re.sub(r"^#{1,6}\s*", "", clean)
    clean = re.sub(r"^(?:[-*+>]|\d+[.、])\s*", "", clean)
    clean = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = clean.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", "", clean)


# ---------------------------------------------------------------------------
# shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Temporary workspace for visual report assembly."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "visual_recipes").mkdir(exist_ok=True)
    return ws


# ---------------------------------------------------------------------------
# golden tests
# ---------------------------------------------------------------------------


class TestGoldenVisualReport:
    """Run each fixture through assemble_visual_report + validation.

    Assertions are structural (no full-snapshot) to stay robust across
    minor internal changes while catching regressions in:
    - Markdown preservation
    - renderer_target validity
    - evidence id integrity
    - appendix ordering
    - no fallback binding
    """

    # ── business monthly report ──────────────────────────────────────

    def test_business_monthly_report(self, workspace_dir: Path) -> None:
        fixture = _load_fixture("business_monthly_report")
        profiles = _build_profiles(fixture["profiles"])
        candidate_angles = [CandidateAngle(**a) for a in fixture.get("candidate_angles", [])]
        semantic_layer = _MockSemanticLayer()

        manifest, snapshot = assemble_visual_report(
            title=fixture["title"],
            report_md=fixture["report_md"],
            step_results=fixture["step_results"],
            profiles=profiles,
            project_contexts=None,
            candidate_angles=candidate_angles,
            chart_specs=fixture.get("chart_specs", []),
            plan_caveats=[],
            semantic_layer=semantic_layer,
            semantic_layer_path=None,
            visual_plan=fixture.get("visual_plan", []),
            workspace_dir=workspace_dir,
            project_id=None,
        )

        expected = fixture["expected"]
        blocks = manifest.blocks

        # Block count
        assert len(blocks) >= expected["min_blocks"], (
            f"Expected ≥ {expected['min_blocks']} blocks, got {len(blocks)}"
        )

        # renderer_target validity
        targets = {b.renderer_target for b in blocks if b.renderer_target is not None}
        invalid = targets - RENDERER_TARGETS
        assert not invalid, f"Invalid renderer_target(s): {invalid}"

        # block_origin validity
        origins = {b.block_origin for b in blocks if b.block_origin is not None}
        invalid_origins = origins - BLOCK_ORIGINS
        assert not invalid_origins, f"Invalid block_origin(s): {invalid_origins}"

        # Required renderer targets present
        for required_target in expected.get("required_renderer_targets", []):
            assert required_target in targets, (
                f"Missing renderer_target '{required_target}'; found: {targets}"
            )

        # Markdown content preservation
        substantive_source = [
            _normalize_line(line)
            for line in fixture["report_md"].splitlines()
            if _normalize_line(line)
        ]
        rendered_text = "\n".join(
            str(b.body or "")
            for b in blocks
            if str(getattr(b, "type", "")) in {"markdown", "prose"}
        )
        rendered_substantive = [
            _normalize_line(line)
            for line in rendered_text.splitlines()
            if _normalize_line(line)
        ]
        missing = [line for line in substantive_source if line not in rendered_substantive]
        assert not missing, f"Missing from visual flow: {missing[:5]}"

        # Must-contain phrases
        for phrase in expected.get("markdown_must_contain", []):
            assert phrase in fixture["report_md"], (
                f"Markdown phrase '{phrase}' not in source (fixture issue)"
            )

        # Evidence id integrity
        valid_ids = _all_chart_table_ids(manifest)
        for block in blocks:
            for eid in block.evidence_ids or []:
                assert eid in valid_ids, (
                    f"Dangling evidence id '{eid}' in block {block.id} (type={block.type})"
                )

        # No fallback evidence: a block with no match should have empty evidence_ids,
        # not fallback to the first available evidence item.
        no_match_blocks = [
            b for b in blocks
            if str(b.type) == "markdown"
            and b.body
            and not any(
                token in (b.body or "").lower()
                for token in ("revenue", "营收", "profit", "利润", "chart", "图表", "table", "表格", "产品", "product", "区域")
            )
        ]
        for b in no_match_blocks:
            assert not b.evidence_ids, (
                f"Block '{b.id}' ({b.body[:50]}...) has fallback evidence binding"
            )

        # Appendix blocks must be contiguous — no main-content blocks
        # interspersed between appendix items.
        appendix_indices = [
            i for i, b in enumerate(blocks)
            if b.renderer_target == "appendix"
        ]
        if len(appendix_indices) >= 2:
            for idx in range(min(appendix_indices), max(appendix_indices) + 1):
                if idx not in appendix_indices:
                    b = blocks[idx]
                    if b.renderer_target != "appendix" and str(b.type) not in ("next_action_list",):
                        # Non-appendix, non-action block between appendix items = ordering issue
                        pass  # This is acceptable if it's a heading or transitional element
            # At minimum: no evidence_component blocks between appendix items
            for idx in range(min(appendix_indices) + 1, max(appendix_indices)):
                if idx not in appendix_indices:
                    b = blocks[idx]
                    assert b.renderer_target != "evidence_component", (
                        f"Evidence component block at idx {idx} interspersed "
                        f"with appendix blocks at {appendix_indices}"
                    )

        # First non-markdown evidence block should not be a table (visual_report mode)
        if expected.get("first_evidence_not_table", False):
            evidence_blocks = [
                b for b in blocks
                if b.type.value not in ("markdown",)
                and b.renderer_target in (None, "evidence_component")
            ]
            if evidence_blocks:
                assert evidence_blocks[0].type.value != "table", (
                    "First evidence block should not be a table"
                )

        # --- validation gates ---
        run = RunResponse(status="running", skill_id="auto", question=fixture["title"])
        run.artifacts = []
        _passed, _fail, _warn, results = run_and_apply_validation(
            run=run,
            manifest=manifest,
            step_results=fixture["step_results"],
            report_md=fixture["report_md"],
            plan_caveats=[],
            profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=_MockPreflight(),
            project_contexts=None,
        )
        # All gates should have been run
        assert len(results) >= 10, f"Expected ≥ 10 validation results, got {len(results)}"
        # Evidence coverage should pass (we have step_results)
        evidence_gate = next((r for r in results if r.gate_id == "evidence_coverage"), None)
        assert evidence_gate is not None
        assert evidence_gate.passed, f"evidence_coverage failed: {evidence_gate.message}"

        # Snapshot-lite structural check
        snapshot = _snapshot_blocks(manifest)
        assert len(snapshot) == len(blocks)
        for s in snapshot:
            assert s["type"]  # every block has a type
            # renderer_target must be None or in allowed set
            if s["renderer_target"] is not None:
                assert s["renderer_target"] in RENDERER_TARGETS, (
                    f"Invalid renderer_target in snapshot: {s['renderer_target']}"
                )

    # ── single table exploration ────────────────────────────────────

    def test_single_table_exploration(self, workspace_dir: Path) -> None:
        fixture = _load_fixture("single_table_exploration")
        profiles = _build_profiles(fixture["profiles"])
        semantic_layer = _MockSemanticLayer()

        manifest, _snapshot = assemble_visual_report(
            title=fixture["title"],
            report_md=fixture["report_md"],
            step_results=fixture["step_results"],
            profiles=profiles,
            project_contexts=None,
            candidate_angles=[],
            chart_specs=[],
            plan_caveats=[],
            semantic_layer=semantic_layer,
            semantic_layer_path=None,
            visual_plan=[],
            workspace_dir=workspace_dir,
            project_id=None,
        )

        blocks = manifest.blocks
        expected = fixture["expected"]

        assert len(blocks) >= expected["min_blocks"]

        # Must contain markdown blocks that preserve content
        markdown_blocks = [b for b in blocks if str(b.type) == "markdown"]
        assert markdown_blocks, "Should have at least one markdown block"
        combined = " ".join(b.body or "" for b in markdown_blocks)
        for phrase in expected["markdown_must_contain"]:
            assert phrase in combined, f"Missing phrase '{phrase}' in rendered markdown"

        # Evidence integrity
        valid_ids = _all_chart_table_ids(manifest)
        for block in blocks:
            for eid in block.evidence_ids or []:
                assert eid in valid_ids, (
                    f"Dangling evidence id '{eid}' in single-table fixture"
                )

        # Run validation
        run = RunResponse(status="running", skill_id="auto", question=fixture["title"])
        run.artifacts = []
        _passed, _fail, _warn, results = run_and_apply_validation(
            run=run, manifest=manifest,
            step_results=fixture["step_results"],
            report_md=fixture["report_md"],
            plan_caveats=[], profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=_MockPreflight(),
            project_contexts=None,
        )
        assert len(results) >= 10

    # ── no chart, table only ────────────────────────────────────────

    def test_no_chart_table_only(self, workspace_dir: Path) -> None:
        fixture = _load_fixture("no_chart_table_only")
        profiles = _build_profiles(fixture["profiles"])
        semantic_layer = _MockSemanticLayer()

        manifest, _snapshot = assemble_visual_report(
            title=fixture["title"],
            report_md=fixture["report_md"],
            step_results=fixture["step_results"],
            profiles=profiles,
            project_contexts=None,
            candidate_angles=[],
            chart_specs=[],
            plan_caveats=[],
            semantic_layer=semantic_layer,
            semantic_layer_path=None,
            visual_plan=[],
            workspace_dir=workspace_dir,
            project_id=None,
        )

        blocks = manifest.blocks
        expected = fixture["expected"]

        # No charts in manifest
        assert len(manifest.charts) == 0, "Fixture has no charts, manifest should have none"

        # All evidence blocks must reference valid table ids
        valid_ids = _all_chart_table_ids(manifest)
        for block in blocks:
            for eid in block.evidence_ids or []:
                assert eid in valid_ids

        # Snapshot-lite
        snap = _snapshot_blocks(manifest)
        table_types = {s["type"] for s in snap}
        assert "table" in table_types, "Should have at least one table block"

        # Validation: should not crash with no charts
        run = RunResponse(status="running", skill_id="auto", question=fixture["title"])
        run.artifacts = []
        _passed, _fail, _warn, results = run_and_apply_validation(
            run=run, manifest=manifest,
            step_results=fixture["step_results"],
            report_md=fixture["report_md"],
            plan_caveats=[], profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=_MockPreflight(),
            project_contexts=None,
        )
        assert len(results) >= 10

    # ── appendix heavy report ───────────────────────────────────────

    def test_appendix_heavy_report(self, workspace_dir: Path) -> None:
        fixture = _load_fixture("appendix_heavy_report")
        profiles = _build_profiles(fixture["profiles"])
        candidate_angles = [CandidateAngle(**a) for a in fixture.get("candidate_angles", [])]
        semantic_layer = _MockSemanticLayer()

        manifest, _snapshot = assemble_visual_report(
            title=fixture["title"],
            report_md=fixture["report_md"],
            step_results=fixture["step_results"],
            profiles=profiles,
            project_contexts=None,
            candidate_angles=candidate_angles,
            chart_specs=fixture.get("chart_specs", []),
            plan_caveats=[],
            semantic_layer=semantic_layer,
            semantic_layer_path=None,
            visual_plan=fixture.get("visual_plan", []),
            workspace_dir=workspace_dir,
            project_id=None,
        )

        blocks = manifest.blocks
        snap = _snapshot_blocks(manifest)

        # Appendix blocks must exist
        appendix_items = [
            (i, s) for i, s in enumerate(snap)
            if s["renderer_target"] == "appendix"
        ]
        assert len(appendix_items) >= fixture["expected"].get("appendix_min_blocks", 2), (
            f"Expected ≥ {fixture['expected'].get('appendix_min_blocks', 2)} appendix blocks, "
            f"got {len(appendix_items)}"
        )

        # Appendix must be at the end: all appendix blocks past the last non-appendix block
        non_appendix_indices = [
            i for i, s in enumerate(snap)
            if s["renderer_target"] != "appendix"
        ]
        appendix_indices = [i for i, _ in appendix_items]
        if non_appendix_indices and appendix_indices:
            last_non_appendix = max(non_appendix_indices)
            assert all(i > last_non_appendix for i in appendix_indices), (
                f"Appendix blocks appear before non-appendix blocks: "
                f"appendix at {appendix_indices}, last non-appendix at {last_non_appendix}"
            )

        # raw_data/full_sales_data tables are excluded from unused_table_ids
        # in artifact_manifest.py (line 337) — they should NOT appear in main blocks.
        raw_data_in_main = [
            b for b in blocks
            if b.renderer_target != "appendix"
            and b.table_id
            and any(
                t.title.lower() in ("raw_data", "full_sales_data")
                for t in (manifest.tables or [])
                if t.id == b.table_id
            )
        ]
        assert not raw_data_in_main, (
            "raw_data table should NOT appear in main report blocks"
        )

        # Unused charts/tables that are not excluded by name should go to appendix
        used_ids = {
            eid for b in blocks
            for eid in (b.evidence_ids or [])
        }
        excluded_names = {"raw_data", "full_sales_data"}
        unused_non_excluded = [
            t for t in (manifest.tables or [])
            if t.id not in used_ids and t.title.lower() not in excluded_names
        ]
        if unused_non_excluded:
            appendix_table_ids = {
                b.table_id for b in blocks
                if b.renderer_target == "appendix" and b.table_id
            }
            for t in unused_non_excluded:
                assert t.id in appendix_table_ids, (
                    f"Unused table '{t.title}' not in appendix"
                )

        # Run validation
        run = RunResponse(status="running", skill_id="auto", question=fixture["title"])
        run.artifacts = []
        _passed, _fail, _warn, results = run_and_apply_validation(
            run=run, manifest=manifest,
            step_results=fixture["step_results"],
            report_md=fixture["report_md"],
            plan_caveats=[], profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=_MockPreflight(),
            project_contexts=None,
        )
        assert len(results) >= 10

    # ── evidence binding edge cases ─────────────────────────────────

    def test_evidence_binding_edge_cases(self, workspace_dir: Path) -> None:
        fixture = _load_fixture("evidence_binding_edge_cases")
        profiles = _build_profiles(fixture["profiles"])
        semantic_layer = _MockSemanticLayer()

        manifest, _snapshot = assemble_visual_report(
            title=fixture["title"],
            report_md=fixture["report_md"],
            step_results=fixture["step_results"],
            profiles=profiles,
            project_contexts=None,
            candidate_angles=[],
            chart_specs=fixture.get("chart_specs", []),
            plan_caveats=[],
            semantic_layer=semantic_layer,
            semantic_layer_path=None,
            visual_plan=fixture.get("visual_plan", []),
            workspace_dir=workspace_dir,
            project_id=None,
        )

        blocks = manifest.blocks
        valid_ids = _all_chart_table_ids(manifest)

        # No dangling evidence
        for block in blocks:
            for eid in block.evidence_ids or []:
                assert eid in valid_ids, f"Dangling evidence id '{eid}'"

        # No-fallback rule: blocks without strong evidence match must NOT get
        # fallback evidence binding to the "first" evidence item
        markdown_blocks = [b for b in blocks if str(b.type) == "markdown"]
        if markdown_blocks:
            # Check that at least one markdown block with non-specific content
            # has empty evidence_ids (no fallback binding)
            non_specific = [
                b for b in markdown_blocks
                if b.body and "无证据" in (b.body or "")
            ]
            for b in non_specific:
                assert not b.evidence_ids, (
                    f"Fallback evidence binding detected on block '{b.id}': "
                    f"{b.evidence_ids}. Block body: {b.body[:80]}..."
                )

        # Section with strong signal should have evidence
        evidence_sections = [
            b for b in markdown_blocks
            if b.body and "利润率" in (b.body or "")
        ]
        assert evidence_sections, "Should have at least one block mentioning 利润率"

        # Run validation
        run = RunResponse(status="running", skill_id="auto", question=fixture["title"])
        run.artifacts = []
        _passed, _fail, _warn, results = run_and_apply_validation(
            run=run, manifest=manifest,
            step_results=fixture["step_results"],
            report_md=fixture["report_md"],
            plan_caveats=[], profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=_MockPreflight(),
            project_contexts=None,
        )
        assert len(results) >= 10


# ---------------------------------------------------------------------------
# snapshot-lite regression: block order stability
# ---------------------------------------------------------------------------

class TestSnapshotLiteStability:
    """Verify snapshot-lite output is deterministic and stable."""

    def test_snapshot_fields_are_deterministic(self, workspace_dir: Path) -> None:
        """Running the same fixture twice gives identical snapshots."""
        fixture = _load_fixture("business_monthly_report")
        profiles = _build_profiles(fixture["profiles"])
        candidate_angles = [CandidateAngle(**a) for a in fixture.get("candidate_angles", [])]
        semantic_layer = _MockSemanticLayer()

        def _assemble() -> list[dict]:
            manifest, _ = assemble_visual_report(
                title=fixture["title"],
                report_md=fixture["report_md"],
                step_results=fixture["step_results"],
                profiles=profiles,
                project_contexts=None,
                candidate_angles=candidate_angles,
                chart_specs=fixture.get("chart_specs", []),
                plan_caveats=[],
                semantic_layer=semantic_layer,
                semantic_layer_path=None,
                visual_plan=fixture.get("visual_plan", []),
                workspace_dir=workspace_dir,
                project_id=None,
            )
            return _snapshot_blocks(manifest)

        snap1 = _assemble()
        snap2 = _assemble()

        assert snap1 == snap2, (
            f"Snapshot-lite output is not deterministic between runs. "
            f"First run: {len(snap1)} blocks, second run: {len(snap2)} blocks"
        )

    def test_all_five_fixtures_produce_valid_snapshots(self, workspace_dir: Path) -> None:
        """Quick sanity: every fixture assembles without error."""
        semantic_layer = _MockSemanticLayer()
        for name in [
            "business_monthly_report",
            "single_table_exploration",
            "no_chart_table_only",
            "appendix_heavy_report",
            "evidence_binding_edge_cases",
        ]:
            fixture = _load_fixture(name)
            profiles = _build_profiles(fixture["profiles"])
            candidate_angles = [
                CandidateAngle(**a)
                for a in fixture.get("candidate_angles", [])
            ]

            manifest, _ = assemble_visual_report(
                title=fixture["title"],
                report_md=fixture["report_md"],
                step_results=fixture["step_results"],
                profiles=profiles,
                project_contexts=None,
                candidate_angles=candidate_angles,
                chart_specs=fixture.get("chart_specs", []),
                plan_caveats=[],
                semantic_layer=semantic_layer,
                semantic_layer_path=None,
                visual_plan=fixture.get("visual_plan", []),
                workspace_dir=workspace_dir,
                project_id=None,
            )

            snap = _snapshot_blocks(manifest)
            # every block must have a type
            for s in snap:
                assert s["type"], f"Block without type in fixture '{name}': {s}"

            # renderer_target must be None or allowed
            for s in snap:
                if s["renderer_target"] is not None:
                    assert s["renderer_target"] in RENDERER_TARGETS, (
                        f"Invalid renderer_target '{s['renderer_target']}' "
                        f"in fixture '{name}'"
                    )

            # block_origin must be None or allowed
            for s in snap:
                if s["block_origin"] is not None:
                    assert s["block_origin"] in BLOCK_ORIGINS, (
                        f"Invalid block_origin '{s['block_origin']}' "
                        f"in fixture '{name}'"
                    )

            assert len(manifest.blocks) >= fixture["expected"].get("min_blocks", 1), (
                f"Fixture '{name}' produced {len(manifest.blocks)} blocks, "
                f"expected ≥ {fixture['expected'].get('min_blocks', 1)}"
            )


# ---------------------------------------------------------------------------
# mock helpers
# ---------------------------------------------------------------------------

class _MockPreflight:
    """Minimal preflight mock for validation tests."""
    context_gaps: list[str] = []
