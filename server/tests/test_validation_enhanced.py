from app.tools.validation import (
    validate_evidence_references,
    validate_source_metadata_on_evidence,
    validate_chart_contract_compatibility,
    validate_project_context_coverage,
)


class TestEvidenceReferences:
    def test_evidence_references_pass(self):
        blocks = [
            {"type": "markdown", "body": "Section A", "evidence_ids": ["chart_abc"]},
            {"type": "markdown", "body": "Section B", "evidence_ids": ["table_xyz"]},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed
        assert result.details["blocks_with_evidence"] == 2
        assert result.details["total_markdown"] == 2

    def test_evidence_references_warn_missing(self):
        blocks = [
            {"type": "markdown", "body": "Section A"},
            {"type": "markdown", "body": "Section B"},
        ]
        result = validate_evidence_references(blocks)
        assert not result.passed
        assert result.details["blocks_with_evidence"] == 0
        assert result.details["total_markdown"] == 2

    def test_evidence_references_mixed(self):
        blocks = [
            {"type": "markdown", "body": "Section A", "evidence_ids": ["chart_a"]},
            {"type": "markdown", "body": "Section B"},
            {"type": "table", "title": "Table"},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed
        assert result.details["blocks_with_evidence"] == 1
        assert result.details["total_markdown"] == 2

    def test_evidence_references_no_markdown_blocks(self):
        blocks = [{"type": "table", "title": "T"}, {"type": "chart", "title": "C"}]
        result = validate_evidence_references(blocks)
        assert result.passed
        assert result.details["blocks_with_evidence"] == 0
        assert result.details["total_markdown"] == 0

    def test_evidence_references_prose_type(self):
        """ReportBlock uses 'prose' type instead of 'markdown'."""
        blocks = [
            {"type": "prose", "data": {"markdown": "text"}, "evidence_ids": ["table_a"]},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed
        assert result.details["blocks_with_evidence"] == 1

    def test_clean_report_with_evidence_ids_passes(self):
        """All markdown blocks have evidence_ids → passed=True, severity='pass'."""
        blocks = [
            {"type": "markdown", "body": "Section A", "evidence_ids": ["chart_abc"]},
            {"type": "markdown", "body": "Section B", "evidence_ids": ["table_xyz"]},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed is True
        assert result.severity == "pass"
        assert "All" in result.message
        assert result.details["blocks_with_evidence"] == 2
        assert result.details["total_markdown"] == 2

    def test_dangling_evidence_ids_detected(self):
        """Dangling IDs referencing non-existent charts/tables now fail validation."""
        blocks = [
            {"type": "markdown", "body": "Section", "evidence_ids": ["nonexistent_chart"]},
        ]
        result = validate_evidence_references(
            blocks,
            chart_ids={"chart_abc"},
            table_ids={"table_xyz"},
        )
        assert result.passed is False
        assert result.severity == "fail"
        assert result.details["dangling_ids"] == ["nonexistent_chart"]

    def test_valid_evidence_ids_pass_with_reference_check(self):
        """Evidence ids referencing actual chart/table ids pass."""
        blocks = [
            {"type": "markdown", "body": "A", "evidence_ids": ["chart_abc"]},
            {"type": "markdown", "body": "B", "evidence_ids": ["table_xyz"]},
        ]
        result = validate_evidence_references(
            blocks,
            chart_ids={"chart_abc", "chart_def"},
            table_ids={"table_xyz"},
        )
        assert result.passed is True
        assert result.severity == "pass"
        assert result.details["blocks_with_evidence"] == 2

    def test_mixed_valid_and_dangling_fails(self):
        """Partial dangling + partial valid evidence ids still fail."""
        blocks = [
            {"type": "markdown", "body": "Good", "evidence_ids": ["chart_ok"]},
            {"type": "markdown", "body": "Bad", "evidence_ids": ["chart_bad"]},
        ]
        result = validate_evidence_references(
            blocks,
            chart_ids={"chart_ok"},
        )
        assert result.passed is False
        assert result.severity == "fail"
        assert result.details["dangling_ids"] == ["chart_bad"]

    def test_dangling_ids_backward_compat_no_ids_provided(self):
        """Without chart_ids/table_ids, behavior is unchanged (checks presence only)."""
        blocks = [
            {"type": "markdown", "body": "Section", "evidence_ids": ["any_id_works"]},
        ]
        result = validate_evidence_references(blocks)
        assert result.passed is True
        assert result.severity == "pass"

    def test_unsupported_block_types_ignored(self):
        """Non-markdown/prose blocks are ignored in evidence check.
        
        Chart/table blocks do not count toward total_markdown.
        Markdown blocks without evidence_ids still cause failure.
        """
        blocks = [
            {"type": "chart", "title": "Chart X", "chart_id": "c1"},
            {"type": "table", "title": "Table Y", "table_id": "t1"},
            {"type": "markdown", "body": "Narrative with no evidence"},
        ]
        result = validate_evidence_references(blocks)
        assert result.details["total_markdown"] == 1
        assert result.details["blocks_with_evidence"] == 0
        assert result.passed is False
        assert result.severity == "fail"


class TestSourceMetadataOnEvidence:
    def test_tables_with_source_pass(self):
        step_results = [
            {"tables": [{"name": "sales", "source": "db/sales.csv"}]},
            {"tables": [{"name": "users", "path": "/data/users.csv"}]},
        ]
        result = validate_source_metadata_on_evidence(step_results)
        assert result.passed
        assert result.details["tables_missing_source"] == []
        assert result.details["charts_missing_source"] == []

    def test_table_without_source_fails(self):
        step_results = [
            {"tables": [{"name": "orphan_table"}]},
        ]
        result = validate_source_metadata_on_evidence(step_results)
        assert not result.passed
        assert "orphan_table" in result.details["tables_missing_source"]

    def test_chart_without_source_fails(self):
        step_results = [
            {"charts": [{"name": "mystery_chart", "type": "bar"}]},
        ]
        result = validate_source_metadata_on_evidence(step_results)
        assert not result.passed
        assert "mystery_chart" in result.details["charts_missing_source"]

    def test_chart_with_source_passes(self):
        step_results = [
            {"charts": [{"name": "revenue_trend", "type": "line", "source": "step_1_analysis.py"}]},
        ]
        result = validate_source_metadata_on_evidence(step_results)
        assert result.passed

    def test_empty_step_results_passes(self):
        result = validate_source_metadata_on_evidence([])
        assert result.passed
        assert result.details["tables_missing_source"] == []
        assert result.details["charts_missing_source"] == []


class TestChartContractCompatibility:
    def test_canonical_types_pass(self):
        step_results = [
            {"charts": [{"name": "trend", "type": "line"}]},
            {"charts": [{"name": "bars", "type": "bar"}, {"name": "pie", "type": "pie"}]},
        ]
        result = validate_chart_contract_compatibility(step_results)
        assert result.passed
        assert result.details["invalid"] == []

    def test_non_canonical_type_fails(self):
        step_results = [
            {"charts": [{"name": "weird", "type": "sunburst"}]},
        ]
        result = validate_chart_contract_compatibility(step_results)
        assert not result.passed
        assert len(result.details["invalid"]) == 1
        assert "sunburst" in result.details["invalid"][0]

    def test_no_charts_passes(self):
        step_results = [{"tables": [{"name": "t"}]}]
        result = validate_chart_contract_compatibility(step_results)
        assert result.passed
        assert result.details["total"] == 0

    def test_mixed_valid_invalid(self):
        step_results = [
            {"charts": [
                {"name": "good", "type": "bar"},
                {"name": "bad", "type": "radar"},
            ]},
        ]
        result = validate_chart_contract_compatibility(step_results)
        assert not result.passed
        assert len(result.details["invalid"]) == 1


class TestProjectContextCoverage:
    def test_both_populated(self):
        result = validate_project_context_coverage(
            project_contexts=[{"kind": "source_routing", "body": "routing"}],
            semantic_layer_data={"metrics": [{"name": "revenue"}]},
        )
        assert result.passed
        assert "populated" in result.message.lower()

    def test_no_context_items_warns(self):
        result = validate_project_context_coverage(
            project_contexts=[],
            semantic_layer_data={"metrics": [{"name": "revenue"}]},
        )
        assert result.passed  # always passes
        assert "No project context items" in result.message

    def test_no_semantic_metrics_warns(self):
        result = validate_project_context_coverage(
            project_contexts=[{"kind": "source_routing"}],
            semantic_layer_data={"metrics": []},
        )
        assert result.passed
        assert "No semantic-layer metrics" in result.message

    def test_both_empty_warns_both(self):
        result = validate_project_context_coverage(
            project_contexts=None,
            semantic_layer_data=None,
        )
        assert result.passed
        msg = result.message
        assert "No project context items" in msg
        assert "No semantic-layer metrics" in msg

    def test_context_count_correct(self):
        result = validate_project_context_coverage(
            project_contexts=[{"a": 1}, {"b": 2}, {"c": 3}],
            semantic_layer_data={"metrics": [{"name": "m1"}, {"name": "m2"}]},
        )
        assert result.details["context_count"] == 3
        assert result.details["sl_metrics"] == 2
