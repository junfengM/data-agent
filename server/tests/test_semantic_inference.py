from app.models.schemas import ColumnProfile, DatasetProfile
from app.tools.semantic_inference import (
    SemanticColumnDraft,
    SemanticDraft,
    SuggestedMetricDraft,
    _column_key,
    _column_meta_by_key,
    _column_keys_by_name,
    _merge_llm_payload,
    _normalize_profile,
    _resolve_column_key,
    infer_semantic_draft_heuristic,
    semantic_draft_to_layer_payload,
    validate_semantic_draft,
)


def _profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_id="ds_1",
        filename="sales.xlsx",
        row_count=100,
        column_count=5,
        columns=[
            ColumnProfile(
                name="订单日期",
                dtype="object",
                non_null_count=100,
                null_count=0,
                null_pct=0,
                unique_count=30,
                sample_values=["2024-01-01", "2024-01-02"],
            ),
            ColumnProfile(
                name="订单ID",
                dtype="int64",
                non_null_count=100,
                null_count=0,
                null_pct=0,
                unique_count=100,
                sample_values=["1001", "1002"],
            ),
            ColumnProfile(
                name="销售额",
                dtype="float64",
                non_null_count=96,
                null_count=4,
                null_pct=4,
                unique_count=80,
                sample_values=["12.5", "18.9"],
            ),
            ColumnProfile(
                name="转化率",
                dtype="float64",
                non_null_count=95,
                null_count=5,
                null_pct=5,
                unique_count=90,
                sample_values=["0.12", "0.19"],
            ),
            ColumnProfile(
                name="客户类型",
                dtype="object",
                non_null_count=100,
                null_count=0,
                null_pct=0,
                unique_count=3,
                sample_values=["新客", "老客"],
            ),
        ],
    )


def test_heuristic_draft_identifies_common_excel_columns():
    draft = infer_semantic_draft_heuristic(profile=_profile(), project_id="p1")
    by_name = {c.source_column: c for c in draft.columns}

    assert by_name["订单日期"].role == "time"
    assert by_name["订单ID"].role == "identifier"
    assert by_name["订单ID"].default_aggregation == "count_distinct"
    assert by_name["销售额"].role == "metric"
    assert by_name["销售额"].semantic_type == "currency_amount"
    assert by_name["销售额"].default_aggregation == "sum"
    assert by_name["转化率"].semantic_type == "rate"
    assert by_name["转化率"].default_aggregation == "avg"
    assert by_name["客户类型"].role == "dimension"

    assert any(m.name == "销售额" for m in draft.suggested_metrics)
    assert any("转化率" in q for q in draft.questions_for_user)


def test_heuristic_does_not_treat_numeric_member_card_ids_as_dates():
    profile = DatasetProfile(
        dataset_id="ds_member",
        filename="members.csv",
        row_count=100,
        column_count=1,
        columns=[
            ColumnProfile(
                name="会员卡号",
                dtype="int64",
                non_null_count=100,
                null_count=0,
                null_pct=0,
                unique_count=100,
                sample_values=["1000137", "2241001", "4439058"],
            ),
        ],
    )

    draft = infer_semantic_draft_heuristic(profile=profile, project_id="p1")

    assert draft.columns[0].role == "identifier"
    assert draft.columns[0].semantic_type == "entity_id"
    assert draft.columns[0].default_aggregation == "count_distinct"


def test_validation_corrects_identifier_and_rate_aggregation():
    draft = SemanticDraft(
        project_id="p1",
        dataset_id="ds_1",
        filename="sales.xlsx",
        columns=[
            SemanticColumnDraft(
                source_column="订单ID",
                role="identifier",
                semantic_type="entity_id",
                default_aggregation="avg",
                confidence=1.0,
            ),
            SemanticColumnDraft(
                source_column="转化率",
                role="metric",
                semantic_type="rate",
                default_aggregation="sum",
                confidence=0.8,
            ),
            SemanticColumnDraft(
                source_column="不存在列",
                role="metric",
                default_aggregation="sum",
            ),
        ],
    )

    validated = validate_semantic_draft(draft, profile=_profile())
    by_name = {c.source_column: c for c in validated.columns}

    assert "不存在列" not in by_name
    assert by_name["订单ID"].default_aggregation == "count_distinct"
    assert by_name["订单ID"].confidence == 1.0
    assert by_name["转化率"].default_aggregation == "avg"
    assert any("unknown column" in w for w in validated.warnings)


def test_confirmed_draft_converts_to_semantic_layer_payload():
    draft = infer_semantic_draft_heuristic(profile=_profile(), project_id="p1")
    payload = semantic_draft_to_layer_payload(draft)

    metrics = {m["source_column"]: m for m in payload["metrics"]}
    dimensions = {d["source_column"]: d for d in payload["dimensions"]}

    assert metrics["销售额"]["formula"] == "SUM(销售额)"
    assert metrics["销售额"]["confirmed_by"] == "user"
    assert metrics["销售额"]["provenance"]["draft_id"] == draft.id
    assert dimensions["订单日期"]["role"] == "time"
    assert dimensions["订单ID"]["role"] == "identifier"
    assert payload["sources"][0]["name"] == "sales.xlsx"


# ── Multi-sheet support tests ─────────────────────────────────────────


def _multi_sheet_profile() -> dict:
    """Simulate a 2-sheet Excel workbook with a shared 'revenue' column."""
    return {
        "filename": "sales.xlsx",
        "dataset_id": "ds_multi",
        "format": "excel",
        "sheet_count": 2,
        "sheet_names": ["Orders", "Refunds"],
        "sheets": [
            {
                "sheet_name": "Orders",
                "source_table": "sales.xlsx#Orders",
                "row_count": 100,
                "columns": [
                    {"name": "order_id", "dtype": "int64", "null_pct": 0.0, "unique_count": 100, "sample_values": [], "source_table": "sales.xlsx#Orders", "sheet_name": "Orders"},
                    {"name": "revenue", "dtype": "float64", "null_pct": 2.0, "unique_count": 90, "sample_values": ["100", "200"], "source_table": "sales.xlsx#Orders", "sheet_name": "Orders"},
                ],
            },
            {
                "sheet_name": "Refunds",
                "source_table": "sales.xlsx#Refunds",
                "row_count": 20,
                "columns": [
                    {"name": "refund_id", "dtype": "int64", "null_pct": 0.0, "unique_count": 20, "sample_values": [], "source_table": "sales.xlsx#Refunds", "sheet_name": "Refunds"},
                    {"name": "revenue", "dtype": "float64", "null_pct": 5.0, "unique_count": 18, "sample_values": ["20", "50"], "source_table": "sales.xlsx#Refunds", "sheet_name": "Refunds"},
                ],
            },
        ],
    }


def test_normalize_dataset_profile():
    """_normalize_profile converts DatasetProfile to workbook dict format."""
    profile = DatasetProfile(
        dataset_id="ds_csv",
        filename="data.csv",
        row_count=10,
        column_count=2,
        columns=[
            ColumnProfile(name="col_a", dtype="int64", non_null_count=10, null_count=0, null_pct=0, unique_count=10),
            ColumnProfile(name="col_b", dtype="object", non_null_count=8, null_count=2, null_pct=20, unique_count=5),
        ],
    )
    norm = _normalize_profile(profile)
    assert norm["filename"] == "data.csv"
    assert norm["format"] == "single_table"
    assert len(norm["sheets"]) == 1
    assert norm["sheets"][0]["sheet_name"] == ""
    assert norm["sheets"][0]["source_table"] == "data.csv"
    assert len(norm["columns"]) == 2
    for col in norm["columns"]:
        assert col["source_table"] == "data.csv"
        assert col["sheet_name"] == ""
        assert "name" in col


def test_normalize_workbook_dict():
    """_normalize_profile enriches workbook dict with flat columns."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    assert len(norm["columns"]) == 4
    assert len(norm["sheets"]) == 2
    # Every flat column has source_table and sheet_name
    for col in norm["columns"]:
        assert "name" in col
        assert "source_table" in col
        assert "sheet_name" in col


def test_column_key_helper():
    assert _column_key("sales.xlsx#Orders", "revenue") == "sales.xlsx#Orders::revenue"
    assert _column_key("", "col") == "::col"


def test_column_meta_and_keys():
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    # revenue appears in both sheets
    assert len(name_keys["revenue"]) == 2
    assert "sales.xlsx#Orders::revenue" in name_keys["revenue"]
    assert "sales.xlsx#Refunds::revenue" in name_keys["revenue"]

    # Unique columns
    assert len(name_keys["order_id"]) == 1
    assert len(name_keys["refund_id"]) == 1


def test_resolve_column_key_unique():
    """Unique column names resolve without source_table."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    assert _resolve_column_key("order_id", "", "", meta, name_keys) == "sales.xlsx#Orders::order_id"
    assert _resolve_column_key("refund_id", "", "", meta, name_keys) == "sales.xlsx#Refunds::refund_id"


def test_resolve_column_key_with_source_table():
    """Same-named columns resolve when source_table is provided."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    assert _resolve_column_key("revenue", "sales.xlsx#Orders", "", meta, name_keys) == "sales.xlsx#Orders::revenue"
    assert _resolve_column_key("revenue", "sales.xlsx#Refunds", "", meta, name_keys) == "sales.xlsx#Refunds::revenue"


def test_resolve_column_key_ambiguous():
    """Same-named columns without source_table return None (ambiguous)."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    result = _resolve_column_key("revenue", "", "", meta, name_keys)
    assert result is None


def test_resolve_column_key_unknown():
    """Unknown column returns None."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    assert _resolve_column_key("nonexistent", "", "", meta, name_keys) is None


def test_multi_sheet_heuristic_draft_preserves_source_table():
    """Multi-sheet heuristic draft keeps both 'revenue' columns distinct."""
    profile = _multi_sheet_profile()
    draft = infer_semantic_draft_heuristic(profile=profile, project_id="p1")

    # Two revenues with different source_table
    revenues = [c for c in draft.columns if c.source_column == "revenue"]
    assert len(revenues) == 2
    orders_rev = [c for c in revenues if c.source_table == "sales.xlsx#Orders"]
    refunds_rev = [c for c in revenues if c.source_table == "sales.xlsx#Refunds"]
    assert len(orders_rev) == 1
    assert len(refunds_rev) == 1
    assert orders_rev[0].sheet_name == "Orders"
    assert refunds_rev[0].sheet_name == "Refunds"


def test_multi_sheet_layer_payload_has_source_table():
    """Layer payload preserves source_table and sheet_name."""
    profile = _multi_sheet_profile()
    draft = infer_semantic_draft_heuristic(profile=profile, project_id="p1")
    payload = semantic_draft_to_layer_payload(draft)

    metrics = payload["metrics"]
    dimensions = payload["dimensions"]
    sources = payload["sources"][0]["columns"]

    # metrics and dimensions have source_table/sheet_name
    for m in metrics:
        assert "source_table" in m
        assert "sheet_name" in m

    for d in dimensions:
        assert "source_table" in d
        assert "sheet_name" in d

    for s in sources:
        assert "source_table" in s
        assert "sheet_name" in s


def test_validation_drops_unknown_llm_column():
    """Validation drops columns not present in profile."""
    profile = _multi_sheet_profile()
    draft = SemanticDraft(
        project_id="p1",
        dataset_id="ds_multi",
        filename="sales.xlsx",
        columns=[
            SemanticColumnDraft(source_column="nonexistent_col", role="metric", default_aggregation="sum"),
        ],
    )
    validated = validate_semantic_draft(draft, profile=profile)
    assert len(validated.columns) == 0
    assert any("unknown column" in w for w in validated.warnings)


def test_validation_drops_ambiguous_column_without_source_table():
    """Ambiguous columns (same name, no source_table) get dropped."""
    profile = _multi_sheet_profile()
    draft = SemanticDraft(
        project_id="p1",
        dataset_id="ds_multi",
        filename="sales.xlsx",
        columns=[
            SemanticColumnDraft(source_column="revenue", role="metric", default_aggregation="sum"),
        ],
    )
    validated = validate_semantic_draft(draft, profile=profile)
    # revenue is ambiguous - appears in 2 sheets, no source_table
    assert len(validated.columns) == 0
    assert any("appears in multiple sheets" in w for w in validated.warnings)


def test_validation_keeps_disambiguated_revenue():
    """Revenue with explicit source_table passes validation."""
    profile = _multi_sheet_profile()
    draft = SemanticDraft(
        project_id="p1",
        dataset_id="ds_multi",
        filename="sales.xlsx",
        columns=[
            SemanticColumnDraft(
                source_column="revenue",
                source_table="sales.xlsx#Orders",
                sheet_name="Orders",
                role="metric",
                default_aggregation="sum",
            ),
        ],
    )
    validated = validate_semantic_draft(draft, profile=profile)
    assert len(validated.columns) == 1
    assert validated.columns[0].source_table == "sales.xlsx#Orders"


def test_merge_llm_uses_column_keys():
    """LLM merge doesn't overwrite same-named columns across sheets."""
    baseline = SemanticDraft(
        project_id="p1",
        dataset_id="ds_multi",
        filename="sales.xlsx",
        columns=[
            SemanticColumnDraft(
                source_column="revenue",
                source_table="sales.xlsx#Orders",
                sheet_name="Orders",
                role="metric",
                default_aggregation="sum",
            ),
            SemanticColumnDraft(
                source_column="revenue",
                source_table="sales.xlsx#Refunds",
                sheet_name="Refunds",
                role="metric",
                default_aggregation="sum",
            ),
        ],
    )
    payload = {
        "columns": [
            {"source_column": "revenue", "source_table": "sales.xlsx#Orders", "role": "metric", "default_aggregation": "avg"},
        ],
    }
    merged = _merge_llm_payload(baseline, payload)
    assert len(merged.columns) == 2
    # Orders revenue got the LLM update to avg
    orders = [c for c in merged.columns if c.source_table == "sales.xlsx#Orders"]
    refunds = [c for c in merged.columns if c.source_table == "sales.xlsx#Refunds"]
    assert orders[0].default_aggregation == "avg"
    assert refunds[0].default_aggregation == "sum"  # unchanged


def test_suggested_metrics_has_source_info():
    """Suggested metrics carry source_table and sheet_name."""
    profile = _multi_sheet_profile()
    draft = infer_semantic_draft_heuristic(profile=profile, project_id="p1")
    revenue_metrics = [m for m in draft.suggested_metrics if m.name == "revenue"]
    assert len(revenue_metrics) == 2
    sources = {(m.source_table, m.sheet_name) for m in revenue_metrics}
    assert ("sales.xlsx#Orders", "Orders") in sources
    assert ("sales.xlsx#Refunds", "Refunds") in sources


def test_validate_suggested_metrics_resolves_source_tables():
    """_validate_suggested_metrics resolves columns via source_table."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    metrics = [
        SuggestedMetricDraft(
            name="Orders Revenue",
            formula="SUM(revenue)",
            source_columns=["revenue"],
            source_table="sales.xlsx#Orders",
            sheet_name="Orders",
        ),
    ]
    from app.tools.semantic_inference import _validate_suggested_metrics
    result = _validate_suggested_metrics(metrics, column_meta=meta, name_to_keys=name_keys)
    assert len(result) == 1
    assert result[0].source_columns == ["revenue"]
    assert result[0].source_table == "sales.xlsx#Orders"
    assert result[0].sheet_name == "Orders"


def test_validate_suggested_metrics_propagates_source_info():
    """source_table/sheet_name propagated from resolved columns when metric lacks them."""
    profile = _multi_sheet_profile()
    norm = _normalize_profile(profile)
    meta = _column_meta_by_key(norm)
    name_keys = _column_keys_by_name(norm)

    # Metric with no source_table/sheet_name, but column is unique (order_id)
    metrics = [
        SuggestedMetricDraft(
            name="Order Count",
            formula="COUNT(order_id)",
            source_columns=["order_id"],
        ),
    ]
    from app.tools.semantic_inference import _validate_suggested_metrics
    result = _validate_suggested_metrics(metrics, column_meta=meta, name_to_keys=name_keys)
    assert len(result) == 1
    assert result[0].source_table == "sales.xlsx#Orders"
    assert result[0].sheet_name == "Orders"


def test_regression_csv_dataset_profile_still_works():
    """CSV/single-sheet DatasetProfile still generates valid draft."""
    profile = _profile()
    draft = infer_semantic_draft_heuristic(profile=profile, project_id="p1")
    by_name = {c.source_column: c for c in draft.columns}
    assert "订单日期" in by_name
    assert "销售额" in by_name
    assert by_name["订单日期"].role == "time"
    assert by_name["销售额"].role == "metric"
