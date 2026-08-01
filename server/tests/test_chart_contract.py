from app.tools.chart_contract import (
    SUPPORTED_CHART_TYPES,
    ALLOWED_CHART_INTENTS,
    INTENT_COMPATIBLE_CHART_TYPES,
    chart_type_valid,
    chart_intent_valid,
    intent_compatible_with_type,
    is_single_series_chart,
    validate_chart_type,
    validate_chart_intent,
    detect_mixed_scale,
    detect_mixed_metric,
    validate_chart,
)


class TestChartTypeConstants:
    def test_all_18_types(self):
        assert len(SUPPORTED_CHART_TYPES) == 18

    def test_essential_types(self):
        essential = {"line", "area", "bar", "scatter", "pie", "histogram",
                      "heatmap", "leaderboard", "sparkline", "funnel",
                      "waterfall", "boxPlot"}
        assert essential.issubset(SUPPORTED_CHART_TYPES)

    def test_every_type_in_intent_map(self):
        for ct in SUPPORTED_CHART_TYPES:
            found = any(ct in types for types in INTENT_COMPATIBLE_CHART_TYPES.values())
            assert found, f"Chart type '{ct}' not in any intent mapping"


class TestChartTypeValidation:
    def test_valid_type(self):
        assert chart_type_valid("bar")

    def test_invalid_type(self):
        assert not chart_type_valid("invalid_chart")

    def test_validate_chart_type_ok(self):
        r = validate_chart_type("line")
        assert r.valid

    def test_validate_chart_type_missing(self):
        r = validate_chart_type("")
        assert not r.valid

    def test_validate_chart_type_unknown(self):
        r = validate_chart_type("sunburst")
        assert not r.valid
        assert "Unsupported" in r.error


class TestChartIntentValidation:
    def test_valid_intents(self):
        for intent in ALLOWED_CHART_INTENTS:
            assert chart_intent_valid(intent)

    def test_empty_intent_valid(self):
        assert chart_intent_valid("")

    def test_unknown_intent(self):
        assert not chart_intent_valid("unknown")

    def test_trend_compatible_with_line(self):
        assert intent_compatible_with_type("trend", "line")

    def test_trend_not_compatible_with_pie(self):
        assert not intent_compatible_with_type("trend", "pie")

    def test_composition_compatible_with_pie(self):
        assert intent_compatible_with_type("composition", "pie")

    def test_validate_intent_type_mismatch(self):
        r = validate_chart_intent("trend", "pie")
        assert not r.valid

    def test_validate_intent_type_match(self):
        r = validate_chart_intent("trend", "line")
        assert r.valid


class TestSingleSeriesDetection:
    def test_leaderboard_is_single_series(self):
        assert is_single_series_chart("leaderboard")

    def test_bar_is_not_single_series(self):
        assert not is_single_series_chart("bar")


class TestMixedScaleDetection:
    def test_similar_values_pass(self):
        r = detect_mixed_scale([100, 120, 90, 110])
        assert r.valid

    def test_ratio_below_threshold_passes(self):
        r = detect_mixed_scale([100, 1000])
        assert r.valid

    def test_extreme_ratio_fails(self):
        r = detect_mixed_scale([1, 100000])
        assert not r.valid

    def test_single_value_passes(self):
        r = detect_mixed_scale([42])
        assert r.valid

    def test_empty_list_passes(self):
        r = detect_mixed_scale([])
        assert r.valid


class TestMixedMetricDetection:
    def test_plain_fields_pass(self):
        r = detect_mixed_metric(["revenue", "orders"], [100, 200])
        assert r.valid

    def test_metric_marker_field_fails(self):
        r = detect_mixed_metric(["kpi_revenue", "kpi_orders"], [1, 2])
        assert not r.valid

    def test_change_pct_field_fails(self):
        r = detect_mixed_metric(["revenue", "change_pct"], [100, 0.15])
        assert not r.valid

    def test_single_field_passes(self):
        r = detect_mixed_metric(["revenue"], [100])
        assert r.valid


class TestValidateChartFull:
    def test_valid_chart_passes_all(self):
        results = validate_chart("bar", intent="comparison")
        assert all(r.valid for r in results)

    def test_invalid_type_stops_early(self):
        results = validate_chart("fake")
        assert len(results) == 1
        assert not results[0].valid

    def test_mismatched_intent_and_type(self):
        results = validate_chart("pie", intent="trend")
        assert any(not r.valid for r in results)

    def test_mixed_scale_with_valid_type(self):
        results = validate_chart("line", y_values=[1, 100000])
        assert any(not r.valid for r in results)

    def test_mixed_metric_fields(self):
        results = validate_chart("bar", y_fields=["revenue", "change_pct"], y_values=[1000, 0.05])
        assert any(not r.valid for r in results)
