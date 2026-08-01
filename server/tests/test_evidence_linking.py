from app.tools.evidence_linking import link_evidence, score_evidence_item, tokenize


def _make_item(**overrides):
    base = {
        "id": "chart_abc",
        "type": "chart",
        "title": "Monthly Revenue Trend",
        "source": "analysis/sales.py",
        "dataset": "ds_chart_abc",
        "spec_id": "spec_monthly_rev",
    }
    base.update(overrides)
    return base


def test_tokenize_splits_on_non_alphanumeric():
    result = tokenize("hello, world! test-data")
    assert "hello" in result
    assert "world" in result
    assert "test" in result
    assert "data" in result
    assert "," not in result
    assert "-" not in result
    assert "!" not in result


def test_tokenize_min_length():
    result = tokenize("a bb ccc d")
    assert "a" not in result
    assert "bb" in result
    assert "ccc" in result
    assert "d" not in result


def test_tokenize_chinese():
    result = tokenize("月度收入趋势 chart")
    assert "月度收入趋势" in result
    assert "chart" in result


def test_score_by_name_overlap():
    item = _make_item(title="Monthly Revenue Trend")
    block = "The monthly revenue trend shows growth"
    score = score_evidence_item(block, item)
    assert score >= 3.0


def test_score_by_source_overlap():
    item = _make_item(title="Unrelated Name", source="analysis/sales.py")
    block = "sales analysis"
    score = score_evidence_item(block, item)
    assert score >= 0.8


def test_score_by_explicit_id():
    item = _make_item(id="chart_market_share", title="Unrelated Name")
    block = "As shown in chart_market_share, the data indicates..."
    score = score_evidence_item(block, item)
    assert score >= 5.0


def test_score_by_dataset():
    item = _make_item(title="Unrelated Name", dataset="ds_market_data")
    block = "market data review"
    score = score_evidence_item(block, item)
    assert score >= 1.0


def test_no_match_scores_zero():
    item = _make_item(
        id="chart_xyz", title="XYZ Widget", source="tools/unrelated.py",
        dataset="ds_xyz", spec_id="spec_xyz",
    )
    block = "completely different content with no overlap whatsoever"
    score = score_evidence_item(block, item)
    assert score == 0.0


def test_link_evidence_returns_top_k():
    items = [
        _make_item(id="chart_high", title="Revenue"),
        _make_item(id="chart_mid", title="Cost"),
        _make_item(id="chart_low", title="Profit"),
        _make_item(id="chart_bottom", title="Headcount"),
    ]
    block = "Revenue is growing significantly this quarter"
    result = link_evidence(block, items, top_k=2, min_score=0.0)
    assert len(result) <= 2
    assert "chart_high" in result


def test_link_evidence_below_threshold_returns_empty():
    items = [
        _make_item(id="chart_x", title="XYZ Widget", source="tools/alpha.py", dataset="ds_xyz",
                   spec_id="spec_xyz"),
        _make_item(id="chart_y", title="ABC Gadget", source="tools/beta.py", dataset="ds_abc",
                   spec_id="spec_abc"),
    ]
    block = "completely different content with no overlap"
    result = link_evidence(block, items, top_k=3, min_score=1.0)
    assert result == []


def test_link_evidence_empty_items():
    result = link_evidence("any text", [], top_k=3, min_score=0.5)
    assert result == []


def test_link_evidence_ranking_order():
    items = [
        _make_item(id="chart_mid", title="Cost Analysis"),
        _make_item(id="chart_high", title="Revenue Analysis"),
        _make_item(id="chart_low", title="Headcount"),
    ]
    block = "Revenue analysis results"
    result = link_evidence(block, items, top_k=3, min_score=0.0)
    assert len(result) >= 1
    assert result[0] == "chart_high"
