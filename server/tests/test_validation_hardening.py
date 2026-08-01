from app.tools.validation import (
    run_validation_gates,
    validate_core_conclusion_visual_support,
    validate_markdown_content_preservation,
    validate_table_dominance,
    validate_visual_evidence_links,
    validate_visual_report_richness,
)


def _gate(results, gate_id):
    return next(result for result in results if result.gate_id == gate_id)


def test_visual_evidence_links_fail_on_dangling_ids():
    result = validate_visual_evidence_links(
        blocks=[
            {
                "id": "kpi-1",
                "type": "kpi_grid",
                "evidence_ids": ["missing-table"],
            }
        ],
        table_ids={"table-1"},
        chart_ids=set(),
    )

    assert result.passed is False
    assert result.severity == "fail"
    assert result.details["dangling_ids"] == ["missing-table"]


def test_visual_report_table_only_richness_fails():
    result = validate_visual_report_richness(
        blocks=[
            {"id": "summary", "type": "markdown", "body": "核心结论", "evidence_ids": ["table-1"]},
            {"id": "table-1", "type": "table", "table_id": "table-1"},
        ],
        delivery_mode="visual_report",
    )

    assert result.passed is False
    assert result.severity == "warning"
    assert result.details["rich_count"] == 0


def test_markdown_content_preservation_detects_missing_original_text():
    report_md = "## 核心结论\n\n销售额增长12%。\n\n- 需要提前备货"
    passed = validate_markdown_content_preservation(
        report_md,
        [{"type": "markdown", "body": "## 核心结论\n\n销售额增长12%。\n\n- 需要提前备货"}],
    )
    failed = validate_markdown_content_preservation(
        report_md,
        [{"type": "markdown", "body": "## 核心结论\n\n销售额增长12%。"}],
    )

    assert passed.passed is True
    assert failed.passed is False
    assert "需要提前备货" in failed.details["missing_lines"]


def test_visual_report_table_first_evidence_fails():
    result = validate_table_dominance(
        blocks=[
            {"id": "summary", "type": "markdown", "body": "核心结论", "evidence_ids": ["chart-1"]},
            {"id": "table-1", "type": "table", "table_id": "table-1"},
            {"id": "chart-1", "type": "chart", "chart_id": "chart-1"},
        ],
        delivery_mode="visual_report",
    )

    assert result.passed is False
    assert result.severity == "fail"
    assert result.details["first_evidence_block_type"] == "table"


def test_core_conclusion_requires_visual_support_for_visual_report():
    result = validate_core_conclusion_visual_support(
        blocks=[
            {
                "id": "summary",
                "type": "markdown",
                "body": "核心结论：收入增长来自华东区域。",
                "evidence_ids": ["table-1"],
                "evidence_priority": "primary",
            },
            {"id": "table-1", "type": "table", "table_id": "table-1"},
        ],
        table_ids={"table-1"},
        chart_ids=set(),
        delivery_mode="visual_report",
    )

    assert result.passed is False
    assert result.severity == "fail"


def test_core_conclusion_passes_when_backed_by_chart():
    result = validate_core_conclusion_visual_support(
        blocks=[
            {
                "id": "summary",
                "type": "markdown",
                "body": "核心结论：收入增长来自华东区域。",
                "evidence_ids": ["chart-1"],
                "evidence_priority": "primary",
            },
            {"id": "chart-1", "type": "chart", "chart_id": "chart-1"},
        ],
        table_ids=set(),
        chart_ids={"chart-1"},
        delivery_mode="visual_report",
    )

    assert result.passed is True
    assert result.severity == "pass"
    assert result.details["chart_supported_core_blocks"] == 1


def test_safety_gates_scan_report_and_structured_blocks():
    step_results = [
        {
            "name": "step",
            "tables": [
                {
                    "id": "table-1",
                    "name": "supporting_table",
                    "path": "supporting_table.csv",
                    "source": "dataset.csv",
                }
            ],
            "charts": [],
        }
    ]
    blocks = [
        {
            "id": "claim-1",
            "type": "markdown",
            "content": "Contact ops@example.com for the raw extract.",
            "evidence_ids": ["table-1"],
        }
    ]

    flagged_text = "sec" + "ret" + " " + "tok" + "en"
    results = run_validation_gates(
        step_results=step_results,
        report_md=f"# Report\n\nA generated summary accidentally included a {flagged_text}.",
        blocks=blocks,
        plan_caveats=["single fixture"],
        profiles=[],
        artifacts=[{"type": "markdown_report"}],
        delivery_mode="markdown",
        context_gaps=[],
        preflight_built=True,
        project_contexts=[],
        semantic_layer_data={"metrics": []},
        manifest_table_ids={"table-1"},
        manifest_chart_ids=set(),
    )

    source_safety = _gate(results, "source_safety")
    sensitive_payload = _gate(results, "sensitive_payload")

    assert source_safety.passed is False
    assert source_safety.severity == "fail"
    assert sensitive_payload.passed is False
    assert sensitive_payload.severity == "warning"


def test_sensitive_payload_does_not_flag_product_codes_as_phone():
    from app.tools.validation import validate_sensitive_payload
    artifacts = [{"title": "test", "content": "商品编码 hg_code 10011170014，SKU 11013370011"}]
    result = validate_sensitive_payload(artifacts)
    issues = result.details.get("issues", []) if result.details else []
    phone_issues = [i for i in issues if "phone" in i.lower()]
    assert len(phone_issues) == 0


def test_sensitive_payload_does_not_flag_barcode_as_phone():
    from app.tools.validation import validate_sensitive_payload
    artifacts = [{"title": "test", "content": "条码 6901234567890，货号 AB123456"}]
    result = validate_sensitive_payload(artifacts)
    issues = result.details.get("issues", []) if result.details else []
    phone_issues = [i for i in issues if "phone" in i.lower()]
    assert len(phone_issues) == 0


def test_sensitive_payload_still_flags_phone_with_context():
    from app.tools.validation import validate_sensitive_payload
    artifacts = [{"title": "test", "content": "联系电话：13800138000"}]
    result = validate_sensitive_payload(artifacts)
    issues = result.details.get("issues", []) if result.details else []
    phone_issues = [i for i in issues if "phone" in i.lower()]
    assert len(phone_issues) >= 1


def test_sensitive_payload_flags_formatted_us_phone():
    from app.tools.validation import validate_sensitive_payload
    artifacts = [{"title": "test", "content": "Call (415) 555-0199 for support"}]
    result = validate_sensitive_payload(artifacts)
    issues = result.details.get("issues", []) if result.details else []
    phone_issues = [i for i in issues if "phone" in i.lower()]
    assert len(phone_issues) >= 1
