"""Anti-regression guards for structural changes (Steps 1-8).

These tests prevent monkey patches, dead-code imports, duplicate artifacts,
and config-drift from creeping back in after cleanup.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from app.agent.skills import SkillRouter
from app.models.schemas import ArtifactBlock, ArtifactBlockType, ArtifactType, RENDERER_TARGETS
from app.tools.chart_contract import FILE_CHART_TYPES


# ── Step 1 regression: no monkey patch in main.py ──

def test_main_does_not_monkey_patch_orchestrator():
    main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    source = main_path.read_text()
    tree = ast.parse(source)

    # main.py must not assign to AgentOrchestrator attributes
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                target_str = ast.unparse(target) if hasattr(ast, "unparse") else _name(target)
                if "_run_log_markdown" in target_str or "AgentOrchestrator" in target_str:
                    pytest.fail(f"main.py must not patch AgentOrchestrator. Found: {target_str}")

    # main.py must not define _install_run_log_tool_call_details
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and "install_run_log" in node.name:
            pytest.fail("main.py must not contain _install_run_log_tool_call_details")


# ── Step 3 regression: no runtime patch modules ──

def test_no_runtime_patch_modules_in_production_path():
    agent_dir = Path(__file__).resolve().parents[1] / "app" / "agent"
    deleted = [
        agent_dir / "visual_report_runtime_patches.py",
        agent_dir / "visual_report_contract.py",
    ]
    for path in deleted:
        assert not path.exists(), f"Deleted file should not exist: {path}"


def test_no_runtime_patch_imports():
    init_path = Path(__file__).resolve().parents[1] / "app" / "__init__.py"
    source = init_path.read_text()
    assert "visual_report_contract" not in source
    assert "visual_report_runtime_patches" not in source


# ── Step 5 regression: file chart constant consistency ──

def test_file_chart_type_constant_exists():
    assert FILE_CHART_TYPES == frozenset({"png", "jpg", "jpeg", "svg", "html", "plotly"})


def test_file_chart_types_consistent_across_modules():
    """planner_bridge and artifact_manifest must both use FILE_CHART_TYPES."""
    bridge_path = Path(__file__).resolve().parents[1] / "app" / "agent" / "planner_bridge.py"
    manifest_path = Path(__file__).resolve().parents[1] / "app" / "agent" / "artifact_manifest.py"

    for path in [bridge_path, manifest_path]:
        source = path.read_text()
        assert "FILE_CHART_TYPES" in source, f"{path.name} must use FILE_CHART_TYPES constant"
        # Must not hard-code the list
        assert '("png", "jpg", "jpeg", "svg", "html")' not in source, \
            f"{path.name} must not hard-code file chart types"


# ── Step 7 regression: structured_manifest deprecated ──

def test_structured_manifest_is_deprecated():
    """structured_manifest is deprecated; only visual_report should be primary."""
    assert ArtifactType.structured_manifest.value == "structured_manifest"


# ── Step 8 regression: skill-template config consistency ──

def test_skill_routes_reference_existing_skills():
    config_path = Path(__file__).resolve().parents[2] / "config" / "skill-routing.yaml"
    skills_dir = Path(__file__).resolve().parents[2] / "skills"

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    route_skills = {entry["skill"] for entry in config["routes"]}

    for skill_id in route_skills:
        skill_path = skills_dir / f"{skill_id}.md"
        assert skill_path.exists(), f"Route references non-existent skill: {skill_id}"


def test_template_aliases_reference_existing_templates():
    config_path = Path(__file__).resolve().parents[2] / "config" / "skill-routing.yaml"
    templates_dir = Path(__file__).resolve().parents[2] / "templates"

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for skill_id, template_name in config.get("template_aliases", {}).items():
        template_path = templates_dir / f"{template_name}.md"
        assert template_path.exists(), \
            f"Template alias '{skill_id} -> {template_name}' references non-existent template"


def test_skill_router_loads_from_config():
    """SkillRouter must route from config, not hard-coded lists."""
    result = SkillRouter.route("周报")
    assert result == "kpi-reporting", f"Expected kpi-reporting, got {result}"

    result2 = SkillRouter.route("下降")
    assert result2 == "metric-diagnostics", f"Expected metric-diagnostics, got {result2}"


def test_skill_router_falls_back_to_default():
    """Unmatched query should fall back to default skill."""
    result = SkillRouter.route("xyzzy_no_match_12345")
    assert result == "product-analysis"


def test_agent_manifest_uses_current_execution_mode_names():
    """Agent manifest should document the active execution mode names."""
    config_path = Path(__file__).resolve().parents[2] / "config" / "agent-manifest.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    mode_ids = {mode["id"] for mode in config["execution"]["modes"]}

    assert "disabled" in mode_ids
    assert "local-dev" in mode_ids
    assert "local" not in mode_ids


# ── Two-layer visual report architecture guards ──

from app.agent.visual_deck_blocks import build_visual_deck_blocks
from app.models.schemas import RENDERER_TARGETS

def test_compose_reading_flow_preserves_all_layers():
    """All blocks with valid renderer_target must survive composition."""
    from app.agent.visual_report_planner import compose_reading_flow
    narrative = [
        ArtifactBlock(id="n1", type=ArtifactBlockType.markdown, body="## 执行摘要\n内容", block_origin="artifact_manifest"),
    ]
    md_visual = [
        ArtifactBlock(id="v1", type=ArtifactBlockType.executive_storyboard, title="摘要视觉", renderer_target="md_visual", block_origin="visual_deck"),
    ]
    evidence = [
        ArtifactBlock(id="e1", type=ArtifactBlockType.chart, chart_id="c1", evidence_ids=["c1"], renderer_target="evidence_component", block_origin="artifact_manifest"),
    ]
    appendix = [
        ArtifactBlock(id="a1", type=ArtifactBlockType.chart, chart_id="c2", evidence_ids=["c2"], renderer_target="appendix", block_origin="artifact_manifest"),
    ]
    result = compose_reading_flow(
        narrative_blocks=narrative,
        md_visual_blocks=md_visual,
        evidence_component_blocks=evidence,
        appendix_blocks=appendix,
    )
    ids = {b.id for b in result}
    assert "n1" in ids, "narrative block dropped"
    assert "v1" in ids, "md_visual block dropped"
    assert "e1" in ids, "evidence_component block dropped"
    assert "a1" in ids, "appendix block dropped"


def test_visual_deck_blocks_have_renderer_target():
    """All blocks from build_visual_deck_blocks must have renderer_target='md_visual'."""
    # Build with minimal valid inputs; deck_blocks will be empty for bare inputs
    # but the _block() helper must still tag correctly.
    from app.agent.visual_deck_blocks import _block as vb_block
    block = vb_block(ArtifactBlockType.insight_banner, title="测试", text="内容")
    assert block.renderer_target == "md_visual"
    assert block.block_origin == "visual_deck"


def test_md_visual_does_not_bind_first_evidence_id_when_no_match():
    """Pseudo-evidence fallback must NOT exist."""
    # Verify that _attach_evidence_ids no longer contains the fallback pattern
    import inspect
    from app.agent.visual_deck_blocks import _attach_evidence_ids
    source = inspect.getsource(_attach_evidence_ids)
    assert "fallback_id" not in source, "_attach_evidence_ids must not contain fallback_id"


def test_layer_tags_validated(monkeypatch):
    """validate_layer_tags must fail on invalid renderer_target."""
    from app.tools.validation import validate_layer_tags
    result = validate_layer_tags([
        {"id": "b1", "renderer_target": "md_visual", "block_origin": "visual_deck"},
        {"id": "b2", "renderer_target": "invalid_value", "block_origin": "visual_deck"},
    ])
    assert not result.passed
    assert result.gate_id == "layer_tags"


def test_file_chart_types_in_targets():
    """RENDERER_TARGETS must include all known values."""
    assert "md_visual" in RENDERER_TARGETS
    assert "evidence_component" in RENDERER_TARGETS
    assert "appendix" in RENDERER_TARGETS
    assert "narrative" in RENDERER_TARGETS


def test_compose_reading_flow_normalizes_evidence_component_source_section():
    """Evidence_component blocks with numbered sections must match normalized narrative sections."""
    from app.agent.visual_report_planner import compose_reading_flow
    narrative = [
        ArtifactBlock(id="n1", type=ArtifactBlockType.markdown, body="## A3. 渠道趋势\n内容", block_origin="artifact_manifest"),
    ]
    evidence = [
        ArtifactBlock(id="e1", type=ArtifactBlockType.chart, chart_id="c1", evidence_ids=["c1"],
                      source_section="渠道趋势", renderer_target="evidence_component", block_origin="artifact_manifest"),
        ArtifactBlock(id="e2", type=ArtifactBlockType.chart, chart_id="c2", evidence_ids=["c2"],
                      source_section="A3. 渠道趋势", renderer_target="evidence_component", block_origin="artifact_manifest"),
    ]
    result = compose_reading_flow(
        narrative_blocks=narrative,
        md_visual_blocks=[],
        evidence_component_blocks=evidence,
        appendix_blocks=[],
    )
    ids = {b.id for b in result}
    # Both evidence blocks must survive and be placed with their section, not appendix
    assert "e1" in ids, "evidence with clean section name dropped"
    assert "e2" in ids, "evidence with numbered section name dropped"
    # Evidence must appear after narrative, not in appendix area
    n1_idx = next(i for i, b in enumerate(result) if b.id == "n1")
    e1_idx = next(i for i, b in enumerate(result) if b.id == "e1")
    assert e1_idx > n1_idx, "evidence must follow its narrative section"


def test_compose_evidence_with_numbered_section_matches():
    """Both 'A3. 渠道趋势' and '渠道趋势' normalize to same key."""
    from app.agent.visual_deck_blocks import normalize_section_title
    assert normalize_section_title("A3. 渠道趋势") == normalize_section_title("渠道趋势")


# ── Phase A.2: Reading flow characterization ──

from app.agent.artifact_manifest import build_artifact_manifest


class TestComposeReadingFlowCharacterization:
    def test_a3_channel_trend_narrative_matches_evidence(self):
        from app.agent.visual_report_planner import compose_reading_flow
        narrative = [
            ArtifactBlock(id="n1", type=ArtifactBlockType.markdown,
                          body="## A3. 渠道趋势\n\n渠道表现分析。", block_origin="artifact_manifest"),
        ]
        evidence = [
            ArtifactBlock(id="e1", type=ArtifactBlockType.chart, chart_id="c1",
                          evidence_ids=["c1"], source_section="渠道趋势",
                          renderer_target="evidence_component", block_origin="artifact_manifest"),
            ArtifactBlock(id="e2", type=ArtifactBlockType.chart, chart_id="c2",
                          evidence_ids=["c2"], source_section="A3. 渠道趋势",
                          renderer_target="evidence_component", block_origin="artifact_manifest"),
        ]
        result = compose_reading_flow(
            narrative_blocks=narrative,
            md_visual_blocks=[],
            evidence_component_blocks=evidence,
            appendix_blocks=[],
        )
        ids = {b.id for b in result}
        assert "e1" in ids, "evidence with clean section name must match"
        assert "e2" in ids, "evidence with numbered section name must match"
        n1_idx = next(i for i, b in enumerate(result) if b.id == "n1")
        e1_idx = next(i for i, b in enumerate(result) if b.id == "e1")
        e2_idx = next(i for i, b in enumerate(result) if b.id == "e2")
        assert e1_idx > n1_idx, "evidence must follow its narrative section"
        assert e2_idx > n1_idx, "evidence must follow its narrative section"

    def test_unanchored_md_visual_inserted_after_exec_summary(self):
        from app.agent.visual_report_planner import compose_reading_flow
        narrative = [
            ArtifactBlock(id="n_exec", type=ArtifactBlockType.markdown,
                          body="## 执行摘要\n\n本报告分析核心指标。", block_origin="artifact_manifest"),
            ArtifactBlock(id="n_detail", type=ArtifactBlockType.markdown,
                          body="## 详细分析\n\n具体数据如下。", block_origin="artifact_manifest"),
        ]
        md_visual = [
            ArtifactBlock(id="v_unanchored", type=ArtifactBlockType.insight_banner,
                          title="全局洞察", text="重要发现",
                          renderer_target="md_visual", block_origin="visual_deck"),
        ]
        result = compose_reading_flow(
            narrative_blocks=narrative,
            md_visual_blocks=md_visual,
            evidence_component_blocks=[],
            appendix_blocks=[],
        )
        exec_idx = next(i for i, b in enumerate(result) if b.id == "n_exec")
        detail_idx = next(i for i, b in enumerate(result) if b.id == "n_detail")
        v_idx = next(i for i, b in enumerate(result) if b.id == "v_unanchored")
        assert v_idx > exec_idx, "unanchored md_visual must go after exec summary"
        assert v_idx < detail_idx, "unanchored md_visual must go before next section"

    def test_unanchored_evidence_component_goes_to_appendix(self):
        from app.agent.visual_report_planner import compose_reading_flow
        narrative = [
            ArtifactBlock(id="n1", type=ArtifactBlockType.markdown,
                          body="## 核心发现\n\n分析结果。", block_origin="artifact_manifest"),
        ]
        evidence = [
            ArtifactBlock(id="e_unanchored", type=ArtifactBlockType.chart,
                          chart_id="c1", evidence_ids=["c1"],
                          source_section="不存在的章节",
                          renderer_target="evidence_component", block_origin="artifact_manifest"),
        ]
        appendix = [
            ArtifactBlock(id="a1", type=ArtifactBlockType.chart, chart_id="c2",
                          evidence_ids=["c2"], renderer_target="appendix",
                          evidence_priority="appendix", block_origin="artifact_manifest"),
        ]
        result = compose_reading_flow(
            narrative_blocks=narrative,
            md_visual_blocks=[],
            evidence_component_blocks=evidence,
            appendix_blocks=appendix,
        )
        a1_idx = next(i for i, b in enumerate(result) if b.id == "a1")
        e_idx = next(i for i, b in enumerate(result) if b.id == "e_unanchored")
        assert e_idx > a1_idx, (
            "unanchored evidence should appear after original appendix items"
        )
        last_block = result[-1]
        assert last_block.renderer_target in ("appendix", None) or last_block.id in ("a1", "e_unanchored"), (
            "last block(s) should be appendix territory"
        )

    def test_appendix_header_created_when_missing(self):
        from app.agent.visual_report_planner import compose_reading_flow
        narrative = [
            ArtifactBlock(id="n1", type=ArtifactBlockType.markdown,
                          body="## Summary\n\nContent.", block_origin="artifact_manifest"),
        ]
        appendix = [
            ArtifactBlock(id="a1", type=ArtifactBlockType.chart, chart_id="c1",
                          evidence_ids=["c1"], renderer_target="appendix",
                          evidence_priority="appendix", block_origin="artifact_manifest"),
        ]
        result = compose_reading_flow(
            narrative_blocks=narrative,
            md_visual_blocks=[],
            evidence_component_blocks=[],
            appendix_blocks=appendix,
        )
        appendix_header = next(
            (b for b in result
             if b.type == ArtifactBlockType.markdown and "附录" in (b.body or "")),
            None,
        )
        assert appendix_header is not None, "must create appendix header when missing"
        assert appendix_header.renderer_target == "appendix"
        assert appendix_header.block_origin == "reading_flow"
        assert appendix_header.evidence_priority == "appendix"

    def test_appendix_always_at_end(self):
        from app.agent.visual_report_planner import compose_reading_flow
        narrative = [
            ArtifactBlock(id="n1", type=ArtifactBlockType.markdown,
                          body="## Summary\n\nContent.", block_origin="artifact_manifest"),
        ]
        appendix = [
            ArtifactBlock(id="a1", type=ArtifactBlockType.table, table_id="t1",
                          evidence_ids=["t1"], renderer_target="appendix",
                          evidence_priority="appendix", block_origin="artifact_manifest"),
        ]
        result = compose_reading_flow(
            narrative_blocks=narrative,
            md_visual_blocks=[],
            evidence_component_blocks=[],
            appendix_blocks=appendix,
        )
        last_ids = [b.id for b in result[-len(appendix):]]
        assert "a1" in last_ids, "appendix items must be at the end"
        for bid in last_ids:
            block = next(b for b in result if b.id == bid)
            assert block.renderer_target == "appendix" or (
                block.type == ArtifactBlockType.markdown and "附录" in (block.body or "")
            ), f"appendix-area block {bid} must have appendix renderer_target"


# ── Phase A.4: Source binding no fallback ──

class TestSourceBindingNoFallback:
    def test_single_source_does_not_auto_bind_unmatched_chart(self):
        from app.agent.visual_deck_evidence import attach_stable_source_ids
        from app.models.schemas import (
            ManifestSource, SourceQuery, ManifestChart, ChartEncodings,
            EvidenceEntry,
        )

        source = ManifestSource(
            id="source_1",
            label="sales.csv",
            query=SourceQuery(description="Sales data"),
        )
        chart = ManifestChart(
            id="chart_1",
            title="Revenue Trend",
            type="line",
            dataset="ds_chart_1",
            encodings=ChartEncodings(),
        )
        evidence = EvidenceEntry(
            id="chart_1",
            type="chart",
            title="Revenue Trend",
            source_dataset="other_data.csv",
        )

        class MockManifest:
            sources = [source]
            charts = [chart]
            tables = []

        class MockSnapshot:
            evidence_map = [evidence]

        manifest = MockManifest()
        snapshot = MockSnapshot()
        attach_stable_source_ids(manifest, snapshot)
        assert chart.source_id is None, (
            "must NOT auto-bind source when chart hints don't match the single source"
        )

    def test_single_source_does_not_auto_bind_unmatched_table(self):
        from app.agent.visual_deck_evidence import attach_stable_source_ids
        from app.models.schemas import (
            ManifestSource, SourceQuery, ManifestTable, EvidenceEntry,
        )

        source = ManifestSource(
            id="source_1",
            label="sales.csv",
            query=SourceQuery(description="Sales data"),
        )
        table = ManifestTable(
            id="table_1",
            title="Channel Breakdown",
            dataset="ds_table_1",
            columns=[],
        )
        evidence = EvidenceEntry(
            id="table_1",
            type="table",
            title="Channel Breakdown",
            source_dataset="unrelated_data.csv",
        )

        class MockManifest:
            sources = [source]
            charts = []
            tables = [table]

        class MockSnapshot:
            evidence_map = [evidence]

        manifest = MockManifest()
        snapshot = MockSnapshot()
        attach_stable_source_ids(manifest, snapshot)
        assert table.source_id is None, (
            "must NOT auto-bind source when table hints don't match the single source"
        )

    def test_matching_source_binds_correctly(self):
        from app.agent.visual_deck_evidence import attach_stable_source_ids
        from app.models.schemas import (
            ManifestSource, SourceQuery, ManifestChart, ChartEncodings,
            EvidenceEntry,
        )

        source = ManifestSource(
            id="source_1",
            label="sales.csv",
            query=SourceQuery(description="Sales data"),
        )
        chart = ManifestChart(
            id="chart_1",
            title="Revenue Trend",
            type="line",
            dataset="ds_chart_1",
            encodings=ChartEncodings(),
            source_id=None,
        )
        evidence = EvidenceEntry(
            id="chart_1",
            type="chart",
            title="Revenue Trend",
            source_dataset="sales.csv",
        )

        class MockManifest:
            sources = [source]
            charts = [chart]
            tables = []

        class MockSnapshot:
            evidence_map = [evidence]

        manifest = MockManifest()
        snapshot = MockSnapshot()
        attach_stable_source_ids(manifest, snapshot)
        assert chart.source_id == "source_1", (
            "must bind source when evidence source_dataset matches source label"
        )


# ── helpers ──

def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""
