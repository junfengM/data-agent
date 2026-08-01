from app.tools.semantic_validation import (
    SemanticMergePreview,
    detect_semantic_ambiguities,
    normalize_metric_name,
    normalize_formula,
    canonical_metric_key,
    extract_metric_signature,
    precheck_semantic_layer_merge,
    validate_semantic_ambiguity,
)


def _m(name, formula="SUM(amount)", grain="day", sources=None, aggregation=None):
    """Build a test metric dict with optional fields."""
    metric = {"name": name, "formula": formula, "grain": grain}
    if sources:
        metric["sources"] = sources
    if aggregation:
        metric["aggregation"] = aggregation
    return metric


# --- detect_semantic_ambiguities tests ---

def test_no_ambiguities():
    metrics = [
        _m("revenue", formula="SUM(amount)"),
        _m("cost", formula="SUM(cost)"),
        _m("profit", formula="revenue - cost"),
    ]
    result = detect_semantic_ambiguities(metrics)
    assert result == []


def test_duplicate_name():
    metrics = [
        _m("revenue"),
        _m("revenue"),
        _m("cost"),
    ]
    result = detect_semantic_ambiguities(metrics)
    assert len(result) >= 1
    dup = next(a for a in result if a.conflict_type == "duplicate_name")
    assert dup.metric_name == "revenue"
    assert dup.details["count"] == 2


def test_conflicting_formula():
    metrics = [
        _m("revenue", formula="SUM(amount)"),
        _m("revenue", formula="SUM(net_amount)"),
    ]
    result = detect_semantic_ambiguities(metrics)
    assert len(result) >= 1
    formula = next(a for a in result if a.conflict_type == "conflicting_formula")
    assert formula.metric_name == "revenue"
    assert len(formula.details["formulas"]) == 2


def test_conflicting_aggregation():
    metrics = [
        _m("revenue", aggregation="sum"),
        _m("revenue", aggregation="avg"),
    ]
    result = detect_semantic_ambiguities(metrics)
    agg = next((a for a in result if a.conflict_type == "conflicting_aggregation"), None)
    assert agg is not None
    assert "sum" in agg.details["aggregations"]
    assert "avg" in agg.details["aggregations"]


def test_conflicting_aggregation_one_explicit():
    """One metric has explicit aggregation, the other doesn't → conflict."""
    metrics = [
        _m("revenue", aggregation="avg"),
        _m("revenue"),  # no aggregation field, defaults to "sum"
    ]
    result = detect_semantic_ambiguities(metrics)
    agg = next((a for a in result if a.conflict_type == "conflicting_aggregation"), None)
    assert agg is not None
    # effective aggregations: avg (explicit) vs sum (implicit)
    assert "sum" in agg.details["aggregations"]


def test_conflicting_grain():
    metrics = [
        _m("revenue", grain="day"),
        _m("revenue", grain="month"),
    ]
    result = detect_semantic_ambiguities(metrics)
    grain = next((a for a in result if a.conflict_type == "conflicting_grain"), None)
    assert grain is not None
    assert "day" in grain.details["grains"]
    assert "month" in grain.details["grains"]


def test_conflicting_source():
    metrics = [
        _m("revenue", sources=["sales.csv"]),
        _m("revenue", sources=["transactions.csv"]),
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is not None
    assert src.metric_name == "revenue"


def test_conflicting_source_column_fallback():
    """Source comparison falls back to source_column / source_dataset."""
    metrics = [
        {"name": "revenue", "formula": "SUM(amount)", "source_column": "revenue_col"},
        {"name": "revenue", "formula": "SUM(amount)", "source_column": "net_revenue_col"},
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is not None


def test_near_duplicate_names():
    metrics = [
        _m("revenue"),
        _m("net_revenue"),
        _m("total_revenue"),
        _m("cost"),
    ]
    result = detect_semantic_ambiguities(metrics)
    near = next((a for a in result if a.conflict_type == "near_duplicate"), None)
    assert near is not None
    names = near.details["names"]
    assert "revenue" in names
    assert "net_revenue" in names
    assert "total_revenue" in names


def test_near_duplicate_prefix_only():
    """Two metrics differ only by prefix, no base name present."""
    metrics = [
        _m("max_cost"),
        _m("min_cost"),
    ]
    result = detect_semantic_ambiguities(metrics)
    near = next((a for a in result if a.conflict_type == "near_duplicate"), None)
    assert near is not None
    assert near.details["base_name"] == "cost"


def test_multiple_conflicts():
    """Same name with different formula AND different grain → multiple conflict types."""
    metrics = [
        _m("revenue", formula="SUM(amount)", grain="day", sources=["sales.csv"]),
        _m("revenue", formula="SUM(net_amount)", grain="month", sources=["transactions.csv"]),
    ]
    result = detect_semantic_ambiguities(metrics)
    types = {a.conflict_type for a in result}
    assert "duplicate_name" in types
    assert "conflicting_formula" in types
    assert "conflicting_grain" in types
    assert "conflicting_source" in types


def test_empty_metrics():
    result = detect_semantic_ambiguities([])
    assert result == []


# --- validate_semantic_ambiguity tests ---

def test_validate_semantic_ambiguity_passes():
    data = {"metrics": [_m("revenue"), _m("cost"), _m("profit")]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is True
    assert result.severity == "pass"
    assert result.details["metrics_checked"] == 3
    assert result.details["ambiguities"] == 0


def test_validate_semantic_ambiguity_fails_on_critical():
    """Pure duplicate (same name, same formula) is a warning, not a blocker."""
    data = {"metrics": [_m("revenue"), _m("revenue")]}
    result = validate_semantic_ambiguity(data)
    # Same name + same formula = mergeable → warning, not fail
    assert result.passed is True
    assert result.severity == "warning"


def test_validate_semantic_ambiguity_fails_on_conflicting_formula():
    data = {"metrics": [
        _m("revenue", formula="SUM(amount)"),
        _m("revenue", formula="SUM(net_amount)"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is False
    assert result.severity == "fail"
    assert result.details["blockers"] >= 1


def test_validate_semantic_ambiguity_warns_on_near_duplicate():
    """Near-duplicate is non-critical → passed=True but severity=warning."""
    data = {"metrics": [_m("revenue"), _m("net_revenue"), _m("total_revenue")]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is True
    assert result.severity == "warning"
    assert result.details["blockers"] == 0
    assert result.details["ambiguities"] >= 1


def test_validate_semantic_ambiguity_no_data():
    result = validate_semantic_ambiguity(None)
    assert result.passed is True
    assert result.severity == "warning"
    assert "No semantic layer metrics" in result.message


def test_validate_semantic_ambiguity_empty_dict():
    result = validate_semantic_ambiguity({})
    assert result.passed is True
    assert result.severity == "warning"
    assert "No semantic layer metrics" in result.message


def test_validate_semantic_ambiguity_empty_metrics():
    result = validate_semantic_ambiguity({"metrics": []})
    assert result.passed is True
    assert result.severity == "warning"
    assert "No semantic layer metrics" in result.message


def test_validate_semantic_ambiguity_only_warnings_passes():
    """Only non-critical warnings (near_duplicate) → passed=True, severity=warning."""
    data = {"metrics": [
        _m("revenue"),
        _m("net_revenue"),
        _m("total_revenue"),
        _m("cost"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is True
    assert result.severity == "warning"
    assert result.details["ambiguities"] >= 1
    assert result.details["blockers"] == 0
    # ambiguity_details should be present
    details = result.details["ambiguity_details"]
    assert len(details) >= 1
    for d in details:
        assert "name" in d
        assert "type" in d
        assert "description" in d


# ── Canonicalization tests ──────────────────────────────────────────────

def test_normalize_metric_name_lower_and_trim():
    assert normalize_metric_name("  Revenue  ") == "revenue"
    assert normalize_metric_name("NET_REVENUE") == "net_revenue"


def test_normalize_metric_name_chinese_parens():
    assert normalize_metric_name("营收（万）") == normalize_metric_name("营收(万)")


def test_normalize_metric_name_dashes():
    assert normalize_metric_name("day–over–day") == normalize_metric_name("day-over-day")
    assert normalize_metric_name("month—over—month") == normalize_metric_name("month-over-month")


def test_normalize_formula():
    assert normalize_formula(" SUM(amount) ") == "sum(amount)"
    assert normalize_formula("AVG（price）") == "avg(price)"


def test_canonical_metric_key_with_source_table():
    m = {"name": "revenue", "source_table": "sales.xlsx#Orders"}
    assert canonical_metric_key(m) == "sales.xlsx#Orders::revenue"


def test_canonical_metric_key_without_source():
    m = {"name": "Revenue", "source_dataset": "sales.csv"}
    assert canonical_metric_key(m) == "sales.csv::revenue"


def test_canonical_metric_key_no_source():
    m = {"name": "profit"}
    assert canonical_metric_key(m) == "::profit"


def test_extract_metric_signature():
    m = {"name": "Revenue", "formula": " SUM(amount) ", "aggregation": "SUM", "grain": "day", "sources": ["sales.csv"]}
    sig = extract_metric_signature(m)
    assert sig["name"] == "revenue"
    assert sig["formula"] == "sum(amount)"
    assert sig["aggregation"] == "sum"
    assert sig["grain"] == "day"
    assert "sales.csv" in sig["sources"]


# ── Severity classification tests ───────────────────────────────────────

def test_severity_duplicate_same_formula_is_warning():
    """Same name + same formula → merge_duplicate warning, not blocker."""
    data = {"metrics": [_m("revenue"), _m("revenue")]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is True
    assert result.severity == "warning"
    assert result.details["blockers"] == 0
    assert result.details["warnings"] >= 1


def test_severity_conflicting_formula_is_blocker():
    data = {"metrics": [
        _m("revenue", formula="SUM(amount)"),
        _m("revenue", formula="SUM(net_amount)"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is False
    assert result.severity == "fail"
    assert result.details["blockers"] >= 1


def test_severity_conflicting_aggregation_is_blocker():
    data = {"metrics": [
        _m("revenue", aggregation="sum"),
        _m("revenue", aggregation="avg"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is False
    assert result.details["blockers"] >= 1


def test_severity_conflicting_grain_is_blocker():
    data = {"metrics": [
        _m("revenue", grain="day"),
        _m("revenue", grain="month"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is False
    assert result.details["blockers"] >= 1


def test_severity_near_duplicate_is_warning():
    data = {"metrics": [
        _m("revenue"),
        _m("net_revenue"),
        _m("total_revenue"),
    ]}
    result = validate_semantic_ambiguity(data)
    assert result.passed is True
    assert result.severity == "warning"
    assert result.details["blockers"] == 0


def test_fix_hint_present_on_warnings():
    data = {"metrics": [_m("revenue"), _m("net_revenue"), _m("total_revenue")]}
    result = validate_semantic_ambiguity(data)
    assert result.fix_hint is not None
    assert "near_duplicate" in result.fix_hint


def test_owner_layer_is_semantic_layer():
    result = validate_semantic_ambiguity({"metrics": [_m("revenue"), _m("revenue")]})
    assert result.owner_layer == "semantic_layer"


def test_ambiguity_details_include_repair_info():
    data = {"metrics": [
        _m("revenue", formula="SUM(amount)"),
        _m("revenue", formula="SUM(net_amount)"),
    ]}
    result = validate_semantic_ambiguity(data)
    for detail in result.details["ambiguity_details"]:
        assert "severity" in detail
        assert "repair_action" in detail
        assert "suggested_resolution" in detail
        assert "affected_metric_indices" in detail


# ── Merge precheck tests ────────────────────────────────────────────────

def test_precheck_can_confirm_on_no_conflicts():
    existing = {"metrics": [
        {"name": "cost", "formula": "SUM(cost)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    assert preview.can_confirm is True
    assert len(preview.blockers) == 0


def test_precheck_blocker_on_conflicting_formula():
    existing = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(net_amount)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    assert preview.can_confirm is False
    assert len(preview.blockers) >= 1


def test_precheck_duplicate_same_formula_is_warning():
    existing = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    assert preview.can_confirm is True
    assert len(preview.warnings) >= 1


def test_precheck_classifies_would_add_and_keep():
    existing = {"metrics": [
        {"name": "cost", "formula": "SUM(cost)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"]},
        {"name": "cost", "formula": "SUM(cost)", "aggregation": "sum", "sources": ["sales.csv"]},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    assert "revenue" in preview.would_add
    assert "cost" in preview.would_keep


def test_precheck_cross_source_warning():
    existing = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["sales.csv"], "source_dataset": "sales.csv"},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)", "aggregation": "sum", "sources": ["refunds.csv"], "source_dataset": "refunds.csv"},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    # Same metric name from different source → should trigger warning
    assert preview.requires_user_confirmation is True


def test_precheck_empty_existing():
    preview = precheck_semantic_layer_merge(None, {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)"},
    ]})
    assert preview.can_confirm is True
    assert len(preview.would_add) == 1


# ── Source comparison tests (upgraded to all sources) ────────────────────

def test_conflicting_source_multi_source_list():
    """Metrics with different multi-source lists → conflicting_source detected."""
    metrics = [
        _m("revenue", sources=["sales.csv", "products.csv"]),
        _m("revenue", sources=["sales.csv"]),
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is not None
    assert src.severity == "blocker"


def test_conflicting_source_table_diff():
    """Same name, different source_table → conflicting_source."""
    metrics = [
        {"name": "revenue", "formula": "SUM(amount)", "source_table": "sales.xlsx#Orders"},
        {"name": "revenue", "formula": "SUM(amount)", "source_table": "sales.xlsx#Refunds"},
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is not None


def test_conflicting_source_column_diff():
    """Same name, different source_column → conflicting_source."""
    metrics = [
        {"name": "revenue", "formula": "SUM(amount)", "source_column": "rev_col_a"},
        {"name": "revenue", "formula": "SUM(amount)", "source_column": "rev_col_b"},
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is not None


def test_same_source_no_conflict():
    """Identical sources → no conflicting_source."""
    metrics = [
        _m("revenue", sources=["sales.csv"]),
        _m("revenue", sources=["sales.csv"]),
    ]
    result = detect_semantic_ambiguities(metrics)
    src = next((a for a in result if a.conflict_type == "conflicting_source"), None)
    assert src is None


# ── Precheck contract tests ───────────────────────────────────────────────

def test_precheck_incoming_metrics_list():
    preview = precheck_semantic_layer_merge(None, {"metrics": [
        {"name": "a", "formula": "SUM(x)"},
        {"name": "b", "formula": "SUM(y)"},
    ]})
    assert preview.incoming_metrics == ["a", "b"]


def test_precheck_would_replace_different_formula():
    existing = {"metrics": [
        {"name": "revenue", "formula": "SUM(old)", "aggregation": "sum", "sources": ["sales.csv"], "source_dataset": "sales.csv"},
    ]}
    incoming = {"metrics": [
        {"name": "revenue", "formula": "SUM(new)", "aggregation": "sum", "sources": ["sales.csv"], "source_dataset": "sales.csv"},
    ]}
    preview = precheck_semantic_layer_merge(existing, incoming)
    assert "revenue" in preview.would_replace
    assert preview.can_confirm is False  # different formula = blocker


def test_precheck_requires_user_confirmation_false_when_clean():
    preview = precheck_semantic_layer_merge(None, {"metrics": [
        {"name": "revenue", "formula": "SUM(amount)"},
    ]})
    assert preview.requires_user_confirmation is False
