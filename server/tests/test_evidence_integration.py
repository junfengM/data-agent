from __future__ import annotations

from app.tools.report_evidence import (
    _check_evidence_integration,
    _scan_hidden_evidence_anchors,
    _table_rows,
    evidence_is_bound_in_blocks,
    infer_evidence_role,
    missing_report_evidence_integrations,
)


class TestTableRowsCompactFallback:
    def test_uses_preview_when_rows_is_int(self):
        table = {
            "name": "category_trends",
            "rows": 238,
            "columns": ["分类", "sales_growth_pct"],
            "preview": [
                {"分类": "帽饰", "sales_growth_pct": 125.0},
            ],
        }
        rows = _table_rows(table)
        assert len(rows) == 1
        assert rows[0]["分类"] == "帽饰"

    def test_uses_rows_when_list(self):
        table = {
            "name": "t",
            "rows": [{"a": 1}, {"a": 2}],
            "preview": [],
        }
        rows = _table_rows(table)
        assert len(rows) == 2

    def test_falls_back_to_data_preview(self):
        table = {
            "name": "t",
            "rows": 100,
            "data": {"preview": [{"x": 1}]},
        }
        rows = _table_rows(table)
        assert len(rows) == 1

    def test_returns_empty_when_no_usable_rows(self):
        table = {"name": "empty", "rows": 0, "preview": []}
        rows = _table_rows(table)
        assert rows == []


class TestInferEvidenceRole:
    def test_intermediate_is_separate_from_debug(self):
        assert infer_evidence_role({"name": "intermediate_calc"}) == "intermediate"

    def test_debug_names_are_debug(self):
        assert infer_evidence_role({"name": "debug_output"}) == "debug"
        assert infer_evidence_role({"name": "raw_data"}) == "debug"

    def test_primary_names_are_primary(self):
        assert infer_evidence_role({"name": "monthly_trends"}) == "primary"
        assert infer_evidence_role({"name": "final_summary"}) == "primary"
        assert infer_evidence_role({"name": "top_ranking"}) == "primary"
        assert infer_evidence_role({"name": "core_metrics"}) == "primary"
        assert infer_evidence_role({"name": "strategy_matrix"}) == "primary"

    def test_charts_default_to_primary(self):
        assert infer_evidence_role({"name": "some_chart", "type": "chart"}) == "primary"

    def test_others_are_supporting(self):
        assert infer_evidence_role({"name": "module_a_detail"}) == "supporting"


class TestEvidenceBoundInBlocks:
    def test_bound_by_evidence_ids(self):
        blocks = [
            {
                "id": "b1",
                "type": "markdown",
                "evidence_ids": ["category_trends"],
            }
        ]
        evidence = {"name": "category_trends"}
        assert evidence_is_bound_in_blocks(evidence, blocks)

    def test_bound_by_source_id(self):
        blocks = [
            {
                "id": "b1",
                "source_id": "category_trends",
            }
        ]
        evidence = {"name": "category_trends"}
        assert evidence_is_bound_in_blocks(evidence, blocks)

    def test_bound_by_chart_id(self):
        blocks = [{"id": "b1", "chart_id": "chart5_growth"}]
        evidence = {"name": "chart5_growth"}
        assert evidence_is_bound_in_blocks(evidence, blocks)

    def test_not_bound_when_no_match(self):
        blocks = [{"id": "b1", "evidence_ids": ["other_table"]}]
        evidence = {"name": "category_trends"}
        assert not evidence_is_bound_in_blocks(evidence, blocks)

    def test_blocks_none_returns_false(self):
        assert not evidence_is_bound_in_blocks({"name": "t"}, None)

    def test_bound_by_manifest_table_id(self):
        blocks = [{"id": "b1", "table_id": "table_a1b2c3d4"}]
        evidence = {"name": "category_trends_2025H2"}
        manifest_tables = [
            {"id": "table_a1b2c3d4", "title": "category_trends_2025H2"},
        ]
        assert evidence_is_bound_in_blocks(
            evidence, blocks,
            manifest_tables=manifest_tables,
        )

    def test_bound_by_manifest_chart_id(self):
        blocks = [{"id": "b1", "chart_id": "chart_x1y2z3w4"}]
        evidence = {"name": "chart5_growth"}
        manifest_charts = [
            {"id": "chart_x1y2z3w4", "title": "chart5_growth", "asset_path": "chart5.html"},
        ]
        assert evidence_is_bound_in_blocks(
            evidence, blocks,
            manifest_charts=manifest_charts,
        )

    def test_not_bound_when_manifest_id_mismatches(self):
        blocks = [{"id": "b1", "table_id": "table_deadbeef"}]
        evidence = {"name": "unrelated_table"}
        manifest_tables = [
            {"id": "table_a1b2c3d4", "title": "category_trends_2025H2"},
        ]
        assert not evidence_is_bound_in_blocks(
            evidence, blocks,
            manifest_tables=manifest_tables,
        )


class TestHiddenEvidenceAnchors:
    def test_scans_tables_and_charts(self):
        md = "text <!-- evidence: tables=category_trends; charts=chart1.html --> more text"
        anchors = _scan_hidden_evidence_anchors(md)
        assert "category_trends" in anchors
        assert "chart1.html" in anchors

    def test_scans_simple_format(self):
        md = "<!-- evidence: category_trends chart1.html -->"
        anchors = _scan_hidden_evidence_anchors(md)
        assert "category_trends" in anchors
        assert "chart1.html" in anchors

    def test_no_anchors_returns_empty(self):
        md = "plain text without anchors"
        anchors = _scan_hidden_evidence_anchors(md)
        assert anchors == set()


class TestCheckEvidenceIntegration:
    def test_block_binding_passes_without_report_md_match(self):
        report_md = "# Report\n\nNo mention of category_trends here."
        evidence = {"name": "category_trends"}
        blocks = [{"id": "b1", "evidence_ids": ["category_trends"]}]
        assert _check_evidence_integration(report_md, evidence, None, blocks)

    def test_hidden_anchor_passes(self):
        report_md = "# Report\n\n<!-- evidence: tables=category_trends -->\n\nSome text."
        evidence = {"name": "category_trends"}
        assert _check_evidence_integration(report_md, evidence, None, None)

    def test_text_match_fallback(self):
        report_md = "# Report\n\nTable category_trends shows growth."
        evidence = {"name": "category_trends", "columns": [], "rows": []}
        assert _check_evidence_integration(report_md, evidence, None, None)

    def test_chart_text_match(self):
        report_md = "# Report\n\n[趋势图](chart1.html) shows the trend."
        evidence = {"name": "chart1", "type": "chart", "path": "chart1.html"}
        assert _check_evidence_integration(report_md, evidence, None, None)


class TestMissingEvidenceWithRoles:
    def test_intermediate_evidence_not_flagged(self):
        results = [
            {
                "tables": [{"name": "intermediate_calc", "columns": ["a"], "rows": []}],
                "charts": [],
            }
        ]
        missing = missing_report_evidence_integrations(
            report_md="No evidence mentioned.",
            execution_results=results,
        )
        assert len(missing) == 0

    def test_primary_evidence_missing_flagged(self):
        results = [
            {
                "tables": [{"name": "monthly_trends", "columns": ["月份", "销售额"], "rows": []}],
                "charts": [],
            }
        ]
        missing = missing_report_evidence_integrations(
            report_md="# Analysis\n\nNo evidence referenced here.",
            execution_results=results,
        )
        assert len(missing) == 1
        assert missing[0]["name"] == "monthly_trends"
        assert missing[0]["role"] == "primary"

    def test_primary_bound_via_blocks_not_missing(self):
        results = [
            {
                "tables": [{"name": "monthly_trends", "columns": ["月份"], "rows": []}],
                "charts": [],
            }
        ]
        blocks = [{"id": "b1", "evidence_ids": ["monthly_trends"]}]
        missing = missing_report_evidence_integrations(
            report_md="No text mention.",
            execution_results=results,
            blocks=blocks,
        )
        assert len(missing) == 0

    def test_chart_missing_with_inline_link_passes(self):
        results = [
            {
                "tables": [],
                "charts": [{"name": "chart1", "type": "chart", "path": "chart1.html"}],
            }
        ]
        missing = missing_report_evidence_integrations(
            report_md="[趋势图](chart1.html) shows growth.",
            execution_results=results,
        )
        assert len(missing) == 0

    def test_no_bottom_list_required(self):
        results = [
            {
                "tables": [],
                "charts": [{"name": "chart1", "type": "chart", "path": "chart1.html"}],
            }
        ]
        missing = missing_report_evidence_integrations(
            report_md="## 趋势分析\n\n[趋势图](chart1.html)\n\n## 结论",
            execution_results=results,
        )
        assert len(missing) == 0
