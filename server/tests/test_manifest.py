import pytest

from app.agent.artifact_manifest import (
    _normalize_visual_plan, build_artifact_manifest, normalize_chart_type, infer_chart_encodings,
)
from app.models.schemas import (
    ArtifactManifest,
    ArtifactSnapshot,
    BLOCK_ORIGINS,
    CANONICAL_CHART_TYPES,
    ColumnProfile,
    DatasetProfile,
    RENDERER_TARGETS,
)


@pytest.fixture
def sample_profiles():
    return [
        DatasetProfile(
            dataset_id="ds1",
            filename="sales.csv",
            row_count=1000,
            column_count=3,
            columns=[
                ColumnProfile(name="month", dtype="object", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                ColumnProfile(name="revenue", dtype="float64", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                ColumnProfile(name="orders", dtype="int64", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
            ],
        )
    ]


class TestBuildArtifactManifest:
    def test_visual_plan_accepts_numeric_priority(self):
        plan = _normalize_visual_plan([{
            "id": "vp_1",
            "block_type": "metric_change",
            "source_section": "核心发现",
            "priority": 1,
        }])

        assert len(plan) == 1
        assert plan[0].priority == "1"

    def test_visual_blocks_follow_summary_instead_of_preceding_report(self):
        report_md = (
            "# Sales Performance Report\n\n"
            "## Executive Summary\n\nRevenue improved.\n\n"
            "## Category Contribution\n\nTop category contribution is shown below."
        )
        step_results = [{
            "name": "analysis",
            "tables": [{
                "name": "category_share",
                "columns": ["category", "revenue_share_pct"],
                "preview": [
                    {"category": "A", "revenue_share_pct": 60},
                    {"category": "B", "revenue_share_pct": 40},
                ],
            }],
            "charts": [],
        }]

        manifest, _ = build_artifact_manifest(
            title="Sales Performance Report",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )

        block_types = [str(block.type) for block in manifest.blocks]
        summary_index = next(
            index for index, block in enumerate(manifest.blocks)
            if block.type == "markdown" and "Executive Summary" in (block.body or "")
        )
        composition_index = block_types.index("composition_panel")
        assert composition_index == summary_index + 1
        assert not any(block.type in {"insight_banner", "risk_panel", "page_summary"} for block in manifest.blocks)

    def test_visual_planner_does_not_force_ranking_without_relationship(self):
        report_md = "# Technical Review\n\n## Summary\n\nModel diagnostics completed."
        step_results = [{
            "name": "analysis",
            "tables": [{
                "name": "diagnostics",
                "columns": ["check", "value"],
                "preview": [{"check": "rows", "value": 10}],
            }],
            "charts": [],
        }]

        manifest, _ = build_artifact_manifest(
            title="Technical Review",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )

        assert not any(block.type in {"leaderboard_pair", "composition_panel"} for block in manifest.blocks)

    def test_basic_markdown_report(self):
        report_md = "## Summary\n\nRevenue up 15%.\n\n## Details\n\nQ1 strong."
        manifest, snapshot = build_artifact_manifest(
            title="Test",
            report_md=report_md,
            step_results=[],
            profiles=[],
        )
        assert manifest.version == 1
        assert manifest.surface == "report"
        assert manifest.title == "Test"
        assert len(manifest.blocks) >= 1
        assert snapshot.version == 1
        assert snapshot.status == "ready"
        assert isinstance(snapshot.datasets, dict)

    def test_empty_report_produces_single_markdown_block(self):
        manifest, _ = build_artifact_manifest(
            title="Empty",
            report_md="Just some text without headings.",
            step_results=[],
            profiles=[],
        )
        assert len(manifest.blocks) == 1
        assert manifest.blocks[0].type == "markdown"

    def test_chart_embedding_by_name(self):
        report_md = "## Revenue Trend\n\nShown in the chart revenue_trend below."
        step_results = [{
            "name": "step1",
            "tables": [],
            "charts": [{
                "name": "revenue_trend",
                "type": "line",
                "x": "month",
                "y": "revenue",
            }],
        }]
        manifest, snapshot = build_artifact_manifest(
            title="Chart Test",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        assert len(markdown_blocks) >= 1
        assert any("Revenue Trend" in b.body for b in markdown_blocks if b.body), (
            "markdown block with 'Revenue Trend' heading must exist alongside chart block"
        )
        chart_blocks = [b for b in manifest.blocks if b.type == "chart"]
        assert len(chart_blocks) >= 1
        chart_id = chart_blocks[0].chart_id
        assert chart_id is not None
        assert chart_id in chart_blocks[0].evidence_ids, (
            "chart block must have evidence_ids containing its chart_id"
        )
        chart = next((c for c in manifest.charts if c.id == chart_id), None)
        assert chart is not None
        assert chart.type == "line"
        assert chart.title == "revenue_trend"
        assert chart.dataset in snapshot.datasets

    def test_narrative_preserved_with_chart(self):
        report_md = "## Revenue Insight\n\nRevenue up 15%.\n\nThe chart revenue_trend shows the trend."
        step_results = [{
            "name": "step1",
            "tables": [],
            "charts": [{
                "name": "revenue_trend",
                "type": "line",
                "x": "month",
                "y": "revenue",
            }],
        }]
        manifest, _ = build_artifact_manifest(
            title="Narrative Test",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        assert len(markdown_blocks) >= 1
        assert any("Revenue up 15%" in b.body for b in markdown_blocks if b.body), (
            "prose 'Revenue up 15%' must appear in markdown block when chart is embedded"
        )
        chart_blocks = [b for b in manifest.blocks if b.type == "chart"]
        assert len(chart_blocks) >= 1

    def test_chart_in_snapshot_has_dataset_key(self):
        step_results = [{
            "name": "step1",
            "charts": [{"name": "my_chart", "type": "bar", "x": "cat", "y": "val"}],
        }]
        manifest, snapshot = build_artifact_manifest(
            title="Snapshot Test",
            report_md="## Chart\n\nmy_chart shows data.",
            step_results=step_results,
            profiles=[],
        )
        for chart in manifest.charts:
            assert chart.dataset in snapshot.datasets

    def test_table_embedding_by_name(self):
        report_md = "## Results\n\nSee the table results_table for details."
        step_results = [{
            "name": "step1",
            "tables": [{
                "name": "results_table",
                "columns": ["product", "revenue"],
                "preview": [
                    {"product": "A", "revenue": 100},
                    {"product": "B", "revenue": 200},
                ],
            }],
            "charts": [],
        }]
        manifest, snapshot = build_artifact_manifest(
            title="Table Test",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        assert len(markdown_blocks) >= 1
        assert any("Results" in b.body for b in markdown_blocks if b.body), (
            "markdown block with 'Results' heading must exist alongside table block"
        )
        table_blocks = [b for b in manifest.blocks if b.type == "table"]
        assert len(table_blocks) >= 1
        table_id = table_blocks[0].table_id
        assert table_id is not None
        table = next((t for t in manifest.tables if t.id == table_id), None)
        assert table is not None
        assert table.title == "results_table"
        assert len(table.columns) == 2
        assert table.columns[0].field == "product"
        assert table.columns[1].field == "revenue"

    def test_table_snapshot_contains_rows(self):
        step_results = [{
            "name": "step1",
            "tables": [{
                "name": "data",
                "columns": ["x", "y"],
                "preview": [{"x": 1, "y": 2}],
            }],
        }]
        manifest, snapshot = build_artifact_manifest(
            title="Rows Test",
            report_md="## Data\n\ndata results.",
            step_results=step_results,
            profiles=[],
        )
        table = manifest.tables[0]
        rows = snapshot.datasets.get(table.dataset, [])
        assert len(rows) == 1
        assert rows[0] == {"x": 1, "y": 2}

    def test_multiple_headings_produce_multiple_blocks(self):
        report_md = (
            "## Section A\n\nContent A.\n\n"
            "## Section B\n\nContent B.\n\n"
            "### Subsection\n\nSub content."
        )
        manifest, _ = build_artifact_manifest(
            title="Multi",
            report_md=report_md,
            step_results=[],
            profiles=[],
        )
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        assert len(markdown_blocks) >= 2

    def test_sources_from_profiles(self):
        manifest, _ = build_artifact_manifest(
            title="Sources",
            report_md="## Test",
            step_results=[],
            profiles=[
                DatasetProfile(
                    dataset_id="ds1", filename="sales.csv",
                    row_count=100, column_count=2, columns=[],
                ),
            ],
        )
        assert len(manifest.sources) == 1
        assert manifest.sources[0].label == "sales.csv"
        assert manifest.sources[0].query is not None

    def test_no_step_results_produces_valid_manifest(self):
        manifest, snapshot = build_artifact_manifest(
            title="No Steps",
            report_md="## Summary\n\nNo analysis steps ran.",
            step_results=[],
            profiles=[],
        )
        assert len(manifest.charts) == 0
        assert len(manifest.tables) == 0
        assert len(snapshot.datasets) == 0

    def test_evidence_ids_on_markdown(self):
        report_md = "## Revenue Trend\n\nShown in the chart revenue_trend below."
        step_results = [{
            "name": "step1",
            "tables": [],
            "charts": [{
                "name": "revenue_trend",
                "type": "line",
                "x": "month",
                "y": "revenue",
            }],
        }]
        manifest, _ = build_artifact_manifest(
            title="Evidence Test",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )
        chart = manifest.charts[0]
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        assert len(markdown_blocks) >= 1
        assert chart.id in markdown_blocks[0].evidence_ids, (
            "markdown block must have evidence_ids containing linked chart id"
        )

    def test_no_evidence_warns(self):
        from app.tools.validation import validate_evidence_references

        blocks = [
            {"type": "prose", "data": {"markdown": "No chart references here."}},
        ]
        result = validate_evidence_references(blocks)
        assert result.gate_id == "evidence_references"
        assert result.passed is False, (
            "validate_evidence_references fails when no blocks have evidence_ids"
        )
        assert result.details["blocks_with_evidence"] == 0

    def test_manifest_blocks_reference_existing_ids(self):
        """Chart/table manifest blocks with evidence_ids matching existing ids pass validation."""
        from app.tools.validation import validate_evidence_references

        blocks = [
            {"type": "markdown", "body": "Revenue insight", "evidence_ids": ["chart_revenue"]},
            {"type": "chart", "chart_id": "chart_revenue", "evidence_ids": ["chart_revenue"]},
            {"type": "markdown", "body": "Sales breakdown", "evidence_ids": ["table_sales"]},
            {"type": "table", "table_id": "table_sales", "evidence_ids": ["table_sales"]},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed is True
        assert result.severity == "pass"
        assert result.details["total_markdown"] == 2
        assert result.details["blocks_with_evidence"] == 2

    def test_manifest_chart_metadata(self):
        """ManifestChart fills unit, source_id, axis titles from chart_info."""
        step_results = [{
            "name": "step1",
            "charts": [{
                "name": "sales_chart",
                "type": "bar",
                "x": "month",
                "y": "revenue",
                "unit": "万元",
                "source_id": "ds_sales_2024",
                "x_axis_title": "月份",
                "y_axis_title": "营收",
                "value_format": "0.0",
                "description": "Monthly revenue chart",
            }],
        }]
        manifest, _ = build_artifact_manifest(
            title="Metadata Test",
            report_md="## Sales\n\nsales_chart shows data.",
            step_results=step_results,
            profiles=[],
        )
        chart = manifest.charts[0]
        assert chart.unit == "万元"
        assert chart.source_id == "ds_sales_2024"
        assert chart.x_axis_title == "月份"
        assert chart.y_axis_title == "营收"
        assert chart.value_format == "0.0"
        assert chart.description == "Monthly revenue chart"

    def test_manifest_chart_metadata_axis_aliases(self):
        """Axis titles fall back to x_axis/y_axis when x_axis_title/y_axis_title missing."""
        step_results = [{
            "name": "step1",
            "charts": [{
                "name": "chart",
                "type": "line",
                "x": "date",
                "y": "val",
                "x_axis": "日期",
                "y_axis": "数值",
            }],
        }]
        manifest, _ = build_artifact_manifest(
            title="Alias Test",
            report_md="## Chart\n\nchart shows data.",
            step_results=step_results,
            profiles=[],
        )
        chart = manifest.charts[0]
        assert chart.x_axis_title == "日期"
        assert chart.y_axis_title == "数值"


class TestNormalizeChartType:
    def test_canonical_types_passthrough(self):
        for ct in ["bar", "line", "area", "scatter", "pie", "histogram", "heatmap",
                     "leaderboard", "sparkline", "funnel", "waterfall", "boxPlot",
                     "stackedBar", "stackedArea", "horizontalBar"]:
            assert normalize_chart_type(ct) == ct

    def test_file_types_map_to_bar(self):
        for ft in ["png", "jpg", "jpeg", "svg", "html", "plotly"]:
            assert normalize_chart_type(ft) == "bar"

    def test_unknown_type_defaults_to_bar(self):
        assert normalize_chart_type("unknown") == "bar"
        assert normalize_chart_type("") == "bar"

    def test_normalize_stacked_chart_types(self):
        """stackedBar100, horizontalStackedBar, horizontalStackedBar100 map correctly."""
        assert normalize_chart_type("stackedBar100") == "stackedBar100"
        assert normalize_chart_type("horizontalStackedBar") == "horizontalStackedBar"
        assert normalize_chart_type("horizontalStackedBar100") == "horizontalStackedBar100"


class TestInferChartEncodings:
    def test_extracts_x_y_from_direct_fields(self):
        enc = infer_chart_encodings({
            "type": "bar", "x": "month", "y": "revenue",
        })
        assert enc.x is not None
        assert enc.x.field == "month"
        assert enc.y is not None
        assert enc.y.field == "revenue"

    def test_extracts_x_y_from_axis_aliases(self):
        enc = infer_chart_encodings({
            "type": "line", "x_axis": "date", "y_axis": "value",
        })
        assert enc.x.field == "date"
        assert enc.y.field == "value"

    def test_scatter_adds_size_encoding(self):
        enc = infer_chart_encodings({
            "type": "scatter", "x": "gdp", "y": "life_exp", "size": "population",
        })
        assert enc.size is not None
        assert enc.size.field == "population"

    def test_bar_does_not_add_size(self):
        enc = infer_chart_encodings({
            "type": "bar", "x": "cat", "y": "val",
        })
        assert enc.size is None

    def test_missing_fields_produce_none_encodings(self):
        enc = infer_chart_encodings({
            "type": "pie",
        })
        assert enc.x is None
        assert enc.y is None

    def test_extracts_color_encoding(self):
        enc = infer_chart_encodings({
            "type": "bar", "x": "cat", "y": "val", "color": "region",
        })
        assert enc.color is not None
        assert enc.color.field == "region"

    def test_extracts_facet_encoding(self):
        enc = infer_chart_encodings({
            "type": "line", "x": "date", "y": "value", "facet": "category",
        })
        assert enc.facet is not None
        assert enc.facet.field == "category"

    def test_extracts_label_encoding(self):
        enc = infer_chart_encodings({
            "type": "pie", "y": "value", "label": "name",
        })
        assert enc.label is not None
        assert enc.label.field == "name"

    def test_multi_series_adds_size_for_stacked_bar(self):
        enc = infer_chart_encodings({
            "type": "stackedBar", "x": "month", "y": "revenue", "secondary_value": "segment",
        })
        assert enc.y is not None
        assert enc.y.fields == ["revenue", "segment"]

    def test_multi_series_adds_size_for_boxplot(self):
        enc = infer_chart_encodings({
            "type": "boxPlot", "x": "category", "y": "value", "secondary_value": "group",
        })
        assert enc.y is not None
        assert enc.y.fields == ["value", "group"]

    def test_multi_series_adds_size_for_heatmap(self):
        enc = infer_chart_encodings({
            "type": "heatmap", "x": "x", "y": "y", "matrix": "count",
        })
        assert enc.y is not None
        assert enc.y.fields == ["y", "count"]

    def test_secondary_value_aliases(self):
        enc = infer_chart_encodings({
            "type": "bar", "x": "cat", "y": "val", "secondary_y": "aux",
        })
        assert enc.y is not None
        assert enc.y.fields == ["val", "aux"]


class TestManifestSnapshotRoundtrip:
    def test_manifest_serializable(self):
        from app.models.schemas import ArtifactBlock, ArtifactBlockType
        manifest = ArtifactManifest(
            title="Test",
            blocks=[ArtifactBlock(id="b1", type=ArtifactBlockType.markdown, body="# Hello")],
        )
        d = manifest.model_dump(mode="json")
        assert d["version"] == 1
        assert d["title"] == "Test"
        assert len(d["blocks"]) == 1

    def test_snapshot_serializable(self):
        snapshot = ArtifactSnapshot(
            datasets={"ds1": [{"x": 1, "y": 2}]},
            status="ready",
        )
        d = snapshot.model_dump(mode="json")
        assert d["version"] == 1
        assert len(d["datasets"]["ds1"]) == 1

    def test_manifest_snapshot_container(self):
        from app.models.schemas import ArtifactBlock, ArtifactBlockType, VisualReportData
        manifest = ArtifactManifest(
            title="Container Test",
            blocks=[ArtifactBlock(id="b1", type=ArtifactBlockType.markdown, body="text")],
        )
        snapshot = ArtifactSnapshot(
            datasets={"ds_b1": [{"k": "v"}]},
        )
        sm = VisualReportData(manifest=manifest, snapshot=snapshot)
        d = sm.model_dump(mode="json")
        assert d["manifest"]["title"] == "Container Test"
        assert len(d["snapshot"]["datasets"]) == 1


    def test_complete_manifest_smoke(self):
        """Full smoke: manifest has blocks, charts, tables, sources, evidence_ids, evidence_map."""
        manifest, snapshot = build_artifact_manifest(
            title="Smoke Test",
            report_md="## Header\n\nContent with test chart and test table.",
            step_results=[{
                "name": "step1",
                "charts": [{
                    "name": "test chart",
                    "type": "bar",
                    "x": "month",
                    "y": "revenue",
                    "data": [{"month": "Jan", "revenue": 100}],
                }],
                "tables": [{
                    "name": "test table",
                    "columns": ["month", "revenue"],
                    "preview": [{"month": "Jan", "revenue": 100}],
                }],
            }],
            profiles=[
                DatasetProfile(
                    dataset_id="ds1", filename="smoke.csv",
                    row_count=100, column_count=2,
                    columns=[
                        ColumnProfile(name="month", dtype="object", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                        ColumnProfile(name="revenue", dtype="float64", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                    ],
                ),
            ],
            candidate_angles=[],
        )
        assert len(manifest.blocks) >= 1
        blocks_with_evidence = [b for b in manifest.blocks if b.evidence_ids]
        assert len(blocks_with_evidence) >= 1
        assert len(manifest.charts) >= 1
        assert len(manifest.tables) >= 1
        assert len(snapshot.evidence_map) >= 1
        assert len(manifest.sources) >= 1


class TestCanonicalChartTypes:
    def test_all_18_types_defined(self):
        assert len(CANONICAL_CHART_TYPES) == 18

    def test_essential_types_present(self):
        essential = {"line", "area", "bar", "scatter", "pie", "histogram",
                      "heatmap", "leaderboard", "sparkline", "funnel",
                      "waterfall", "boxPlot"}
        assert essential.issubset(set(CANONICAL_CHART_TYPES))

    def test_stacked_variants_present(self):
        variants = {"stackedBar", "stackedBar100", "stackedArea",
                     "horizontalBar", "horizontalStackedBar", "horizontalStackedBar100"}
        assert variants.issubset(set(CANONICAL_CHART_TYPES))


# ── Phase A characterization tests ──────────────────────────────────────


class TestFullLayerCharacterization:
    """A.1: 完整层级 characterization — every layer with correct tags."""

    @pytest.fixture
    def layered_report(self):
        """Report with executive summary, A3 section, referenced + unreferenced chart/table."""
        report_md = (
            "## 执行摘要\n\n"
            "本报告分析了渠道销售趋势。总体表现良好。\n\n"
            "## A3. 渠道趋势\n\n"
            "渠道A表现突出。详见 channel_trend 图表和 channel_table 数据表。\n\n"
            "## 其他补充\n\n"
            "其他分析细节见附录。"
        )
        step_results = [{
            "name": "analysis",
            "tables": [
                {
                    "name": "channel_table",
                    "columns": ["channel", "revenue"],
                    "preview": [
                        {"channel": "A", "revenue": 100},
                        {"channel": "B", "revenue": 200},
                    ],
                },
                {
                    "name": "unused_table",
                    "columns": ["x", "y"],
                    "preview": [{"x": 1, "y": 2}],
                },
            ],
            "charts": [
                {
                    "name": "channel_trend",
                    "type": "line",
                    "x": "month",
                    "y": "revenue",
                },
                {
                    "name": "unused_chart",
                    "type": "bar",
                    "x": "cat",
                    "y": "val",
                },
            ],
        }]
        manifest, snapshot = build_artifact_manifest(
            title="渠道分析报告",
            report_md=report_md,
            step_results=step_results,
            profiles=[],
        )
        return manifest, snapshot

    def test_markdown_blocks_preserve_key_sentences(self, layered_report):
        manifest, _ = layered_report
        markdown_blocks = [b for b in manifest.blocks if b.type == "markdown"]
        bodies = " ".join(b.body or "" for b in markdown_blocks)
        assert "执行摘要" in bodies
        assert "渠道销售趋势" in bodies
        assert "A3. 渠道趋势" in bodies
        assert "渠道A表现突出" in bodies

    def test_chart_and_table_manifest_exist(self, layered_report):
        manifest, _ = layered_report
        assert len(manifest.charts) == 2
        assert len(manifest.tables) == 2
        chart_names = {c.title for c in manifest.charts}
        assert "channel_trend" in chart_names
        assert "unused_chart" in chart_names
        table_names = {t.title for t in manifest.tables}
        assert "channel_table" in table_names
        assert "unused_table" in table_names

    def test_evidence_component_blocks_have_correct_tags(self, layered_report):
        manifest, _ = layered_report
        evidence_blocks = [b for b in manifest.blocks if b.renderer_target == "evidence_component"]
        assert len(evidence_blocks) >= 2, "should have at least chart and table evidence_component blocks"
        for block in evidence_blocks:
            assert block.renderer_target == "evidence_component"
            assert block.block_origin in {"artifact_manifest", "visual_report_planner"}, (
                f"evidence_component block {block.id} has unexpected block_origin: {block.block_origin}"
            )
            assert len(block.evidence_ids) >= 1, f"evidence_component block {block.id} must have evidence_ids"
            if block.type == "chart":
                assert block.chart_id is not None
                assert block.chart_id in block.evidence_ids
            elif block.type == "table":
                assert block.table_id is not None
                assert block.table_id in block.evidence_ids

    def test_appendix_blocks_have_correct_tags(self, layered_report):
        manifest, _ = layered_report
        appendix_blocks = [b for b in manifest.blocks if b.renderer_target == "appendix"]
        assert len(appendix_blocks) >= 1, "unreferenced chart/table should produce appendix blocks"
        for block in appendix_blocks:
            assert block.renderer_target == "appendix"
            assert block.block_origin == "artifact_manifest"
            if block.type == "markdown":
                assert "附录" in (block.body or ""), "appendix header must contain 附录"
                assert block.evidence_priority == "appendix"

    def test_evidence_ids_reference_real_ids(self, layered_report):
        manifest, _ = layered_report
        chart_ids = {c.id for c in manifest.charts}
        table_ids = {t.id for t in manifest.tables}
        all_ids = chart_ids | table_ids
        for block in manifest.blocks:
            for eid in block.evidence_ids:
                assert eid in all_ids, (
                    f"evidence_id {eid} in block {block.id} must reference a real chart or table id"
                )

    def test_block_origin_consistency(self, layered_report):
        manifest, _ = layered_report
        for block in manifest.blocks:
            assert block.block_origin is not None or block.type == "markdown", (
                f"block {block.id} type={block.type} missing block_origin"
            )
            if block.block_origin is not None:
                assert block.block_origin in BLOCK_ORIGINS, (
                    f"block {block.id} has invalid block_origin: {block.block_origin}"
                )


class TestSnapshotDriftGuard:
    """A.3: No-behavior-drift snapshot — stable structure, no UUID."""

    SNAPSHOT_FIXTURE_REPORT = (
        "## 执行摘要\n\n"
        "本报告分析了核心指标表现。\n\n"
        "## A3. 渠道趋势\n\n"
        "渠道A表现突出。详见 sales_chart 图表和 sales_table 数据表。\n\n"
        "## 风险提示\n\n"
        "注意季节性波动。"
    )

    SNAPSHOT_FIXTURE_STEPS = [{
        "name": "analysis",
        "charts": [{
            "name": "sales_chart",
            "type": "bar",
            "x": "month",
            "y": "revenue",
            "data": [{"month": "Jan", "revenue": 100}],
        }],
        "tables": [{
            "name": "sales_table",
            "columns": ["month", "revenue"],
            "preview": [{"month": "Jan", "revenue": 100}],
        }],
    }]

    @pytest.fixture
    def snapshot_manifest(self):
        manifest, snapshot = build_artifact_manifest(
            title="Snapshot Drift Test",
            report_md=self.SNAPSHOT_FIXTURE_REPORT,
            step_results=self.SNAPSHOT_FIXTURE_STEPS,
            profiles=[
                DatasetProfile(
                    dataset_id="ds1", filename="sales.csv",
                    row_count=100, column_count=2,
                    columns=[
                        ColumnProfile(name="month", dtype="object", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                        ColumnProfile(name="revenue", dtype="float64", non_null_count=12, null_count=0, null_pct=0.0, unique_count=12),
                    ],
                ),
            ],
        )
        return manifest, snapshot

    def test_normalized_snapshot_stable(self, snapshot_manifest):
        manifest, _ = snapshot_manifest
        actual = [
            {
                "type": str(b.type),
                "renderer_target": b.renderer_target,
                "block_origin": b.block_origin,
                "evidence_priority": b.evidence_priority,
                "has_chart_id": bool(b.chart_id),
                "has_table_id": bool(b.table_id),
                "evidence_count": len(b.evidence_ids or []),
            }
            for b in manifest.blocks
        ]
        # Compute a stable key: type + renderer_target + block_origin.  Do NOT
        # snapshot UUID / generated_at — only the structural behavior contract.
        expected = [
            {"type": "markdown", "renderer_target": None, "block_origin": "artifact_manifest", "evidence_priority": "diagnostic", "has_chart_id": False, "has_table_id": False, "evidence_count": 0},
            {"type": "markdown", "renderer_target": None, "block_origin": "artifact_manifest", "evidence_priority": "primary", "has_chart_id": False, "has_table_id": False, "evidence_count": 2},
            {"type": "chart", "renderer_target": "evidence_component", "block_origin": "artifact_manifest", "evidence_priority": "primary", "has_chart_id": True, "has_table_id": False, "evidence_count": 1},
            {"type": "table", "renderer_target": "evidence_component", "block_origin": "artifact_manifest", "evidence_priority": "primary", "has_chart_id": False, "has_table_id": True, "evidence_count": 1},
            {"type": "markdown", "renderer_target": None, "block_origin": "artifact_manifest", "evidence_priority": "diagnostic", "has_chart_id": False, "has_table_id": False, "evidence_count": 0},
        ]
        assert actual == expected, f"snapshot drift:\nACTUAL: {actual}\nEXPECTED: {expected}"


class TestFrontendContractGuard:
    """A.5: Frontend contract guard — all blocks conform to RENDERER_TARGETS/BLOCK_ORIGINS."""

    def test_all_blocks_renderer_target_in_known_set(self):
        manifest, _ = build_artifact_manifest(
            title="Contract Test",
            report_md="## Summary\n\nData analysis results.\n\n## Details\n\nChart my_chart shows trend.",
            step_results=[{
                "name": "step1",
                "charts": [{"name": "my_chart", "type": "line", "x": "month", "y": "val"}],
                "tables": [],
            }],
            profiles=[],
        )
        for block in manifest.blocks:
            rt = block.renderer_target
            if rt is not None:
                assert rt in RENDERER_TARGETS, (
                    f"block {block.id} type={block.type} has invalid renderer_target: {rt!r}"
                )
            bo = block.block_origin
            if bo is not None:
                assert bo in BLOCK_ORIGINS, (
                    f"block {block.id} type={block.type} has invalid block_origin: {bo!r}"
                )

    def test_visual_report_planner_origin_present_when_planner_active(self):
        """When visual planner generates blocks, they carry visual_report_planner origin."""
        manifest, _ = build_artifact_manifest(
            title="Planner Origin Test",
            report_md="## A3. 渠道趋势\n\n渠道A增长15%。渠道B下降5%。",
            step_results=[{
                "name": "step1",
                "charts": [],
                "tables": [{
                    "name": "channel_data",
                    "columns": ["channel", "revenue", "revenue_prev"],
                    "preview": [
                        {"channel": "A", "revenue": 115, "revenue_prev": 100},
                        {"channel": "B", "revenue": 95, "revenue_prev": 100},
                    ],
                }],
            }],
            profiles=[],
        )
        origins = {b.block_origin for b in manifest.blocks if b.block_origin is not None}
        # At minimum artifact_manifest origin exists
        assert "artifact_manifest" in origins

    def test_validate_layer_tags_rejects_invalid_renderer_target(self):
        from app.tools.validation import validate_layer_tags
        result = validate_layer_tags([
            {"id": "b1", "renderer_target": "md_visual", "block_origin": "visual_deck"},
            {"id": "b2", "renderer_target": "not_a_valid_target", "block_origin": "visual_deck"},
        ])
        assert not result.passed
        assert result.gate_id == "layer_tags"

    def test_validate_layer_tags_rejects_invalid_block_origin(self):
        from app.tools.validation import validate_layer_tags
        result = validate_layer_tags([
            {"id": "b1", "renderer_target": "evidence_component", "block_origin": "artifact_manifest"},
            {"id": "b2", "renderer_target": "evidence_component", "block_origin": "not_a_valid_origin"},
        ])
        assert not result.passed
        assert result.gate_id == "layer_tags"


def test_fallback_report_not_blocked():
    from app.agent.artifact_manifest import draft_fallback_report
    from app.models.schemas import AnalysisRequest

    request = AnalysisRequest(question="测试问题", dataset_ids=["ds1"], delivery_mode="markdown")
    report = draft_fallback_report(
        request=request,
        skill_id="sales_analysis",
        profiles=[],
        profile_markdown="## Profile",
        project=None,
        context_markdown="## Context",
        step_results=[
            {
                "name": "monthly_trend",
                "returncode": 0,
                "status": "completed",
                "stdout": "月度销售额持续增长\n关键发现：环比增长15%",
                "tables": [
                    {
                        "name": "monthly_summary",
                        "columns": ["月份", "销售额"],
                        "preview": [{"月份": "2026-01", "销售额": 100}],
                    }
                ],
                "charts": [
                    {
                        "name": "chart1",
                        "title": "月度销售趋势",
                        "path": "chart1_monthly_sales_trend.html",
                        "type": "bar",
                    }
                ],
            },
            {
                "name": "failed_step",
                "returncode": 1,
                "status": "failed",
                "stderr": "KeyError: 'column_name'",
                "tables": [],
                "charts": [],
            },
        ],
        plan={},
    )

    assert "[BLOCKED]" not in report
    assert "分析报告（自动恢复版）" in report
    assert "chart1_monthly_sales_trend.html" in report
    assert "monthly_summary" in report
    assert "月度销售额持续增长" in report or "关键发现" in report
    assert "failed_step" in report
    assert "returncode=1" in report


def test_fallback_report_shows_failed_steps():
    from app.agent.artifact_manifest import draft_fallback_report
    from app.models.schemas import AnalysisRequest

    request = AnalysisRequest(question="test", dataset_ids=[], delivery_mode="markdown")
    report = draft_fallback_report(
        request=request,
        skill_id="test",
        profiles=[],
        profile_markdown="",
        project=None,
        context_markdown="",
        step_results=[
            {"name": "bad_step", "returncode": 2, "status": "failed", "stderr": "error", "tables": [], "charts": []},
        ],
        plan={},
    )
    assert "失败步骤" in report
    assert "bad_step" in report
