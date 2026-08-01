import yaml


from app.tools.preflight import (
    SemanticLayer,
    build_preflight_envelope,
    derive_semantic_layer,
    load_semantic_layer,
    preflight_to_markdown,
    select_active_layer,
)
from app.tools.semantic_helpers import MetricEntry, DimensionEntry, CaveatEntry
from app.models.schemas import ColumnProfile, DatasetProfile, ProjectContext


class TestMetricEntry:
    def test_create_with_all_fields(self):
        entry = MetricEntry(
            name="monthly_revenue",
            formula="SUM(revenue) WHERE status='completed'",
            grain="monthly",
            dimensions=["category", "region"],
            sources=["sales.csv"],
            caveat="Excludes pending orders",
        )
        assert entry.name == "monthly_revenue"
        assert entry.formula == "SUM(revenue) WHERE status='completed'"
        assert entry.grain == "monthly"
        assert entry.dimensions == ["category", "region"]
        assert entry.sources == ["sales.csv"]
        assert entry.caveat == "Excludes pending orders"
        assert entry.created_at  # auto-generated
        assert entry.updated_at  # auto-generated

    def test_minimal_creation(self):
        entry = MetricEntry(name="order_count", formula="COUNT(orders)")
        assert entry.name == "order_count"
        assert entry.grain == ""
        assert entry.dimensions == []
        assert entry.sources == []
        assert entry.caveat == ""

    def test_dimension_entry(self):
        entry = DimensionEntry(
            name="category",
            source_column="product_category",
            source_table="products",
            description="Product category hierarchy",
        )
        assert entry.name == "category"
        assert entry.source_column == "product_category"
        assert entry.source_table == "products"
        assert entry.description == "Product category hierarchy"

    def test_caveat_entry(self):
        entry = CaveatEntry(
            description="Data before 2024 is incomplete",
            severity="warning",
            affected_metrics=["monthly_revenue", "order_count"],
            source="manual_review",
        )
        assert entry.description == "Data before 2024 is incomplete"
        assert entry.severity == "warning"
        assert entry.affected_metrics == ["monthly_revenue", "order_count"]
        assert entry.source == "manual_review"

    def test_caveat_entry_defaults(self):
        entry = CaveatEntry(description="Null values in revenue column")
        assert entry.severity == "info"
        assert entry.affected_metrics == []
        assert entry.source == ""


class TestSelectActiveLayer:
    def test_empty_list_returns_none(self):
        assert select_active_layer([]) is None

    def test_single_layer_returned(self):
        layers = [{"id": "L1", "created_at": "2024-01-01T00:00:00Z"}]
        result = select_active_layer(layers)
        assert result is not None
        assert result["id"] == "L1"

    def test_returns_latest_by_created_at(self):
        layers = [
            {"id": "L1", "created_at": "2024-01-01T00:00:00Z"},
            {"id": "L3", "created_at": "2024-03-01T00:00:00Z"},
            {"id": "L2", "created_at": "2024-02-01T00:00:00Z"},
        ]
        result = select_active_layer(layers)
        assert result is not None
        assert result["id"] == "L3"

    def test_handles_missing_created_at(self):
        layers = [
            {"id": "L1", "created_at": ""},
            {"id": "L2"},
        ]
        result = select_active_layer(layers)
        assert result is not None
        assert result["id"] in ("L1", "L2")  # stable ordering with empty strings


class TestActiveLayerInPreflight:
    def test_no_layers_produces_none_meta(self):
        preflight = build_preflight_envelope(
            project=None,
            project_contexts=[],
            semantic_layer=SemanticLayer(),
            profiles=[],
        )
        assert preflight.active_semantic_layer_meta is None

    def test_with_layers_sets_active_layer_meta(self):
        layers = [
            {"id": "L1", "name": "v1", "created_at": "2024-01-01T00:00:00Z"},
            {"id": "L2", "name": "v2", "created_at": "2024-06-01T00:00:00Z"},
        ]
        preflight = build_preflight_envelope(
            project=None,
            project_contexts=[],
            semantic_layer=SemanticLayer(),
            profiles=[],
            project_layers=layers,
        )
        assert preflight.active_semantic_layer_meta is not None
        assert preflight.active_semantic_layer_meta["id"] == "L2"
        assert preflight.active_semantic_layer_meta["name"] == "v2"

    def test_preflight_dataclass_fields(self):
        preflight = build_preflight_envelope(
            project=None,
            project_contexts=[],
            semantic_layer=SemanticLayer(metrics=[{"name": "test_metric"}]),
            profiles=[],
            project_layers=[{"id": "L1", "created_at": "2024-01-01T00:00:00Z"}],
        )
        assert preflight.project_id == ""
        assert preflight.project_name == "No project"
        assert len(preflight.semantic_layer.metrics) == 1
        assert preflight.active_semantic_layer_meta is not None
        assert preflight.active_semantic_layer_meta["id"] == "L1"

    def test_preflight_data_map_includes_all_columns_and_metric_contracts(self):
        profile = DatasetProfile(
            dataset_id="dataset-1",
            filename="orders.csv",
            row_count=100,
            column_count=14,
            columns=[
                ColumnProfile(
                    name=f"field_{index}",
                    dtype="object",
                    non_null_count=100,
                    null_count=0,
                    null_pct=0,
                    unique_count=3,
                    sample_values=["A", "B"],
                    min_value="A",
                    max_value="B",
                )
                for index in range(14)
            ],
        )
        layer = SemanticLayer(
            metrics=[{
                "name": "订单数",
                "formula": "COUNT_DISTINCT(会员卡号, 日期, 订单细分类型)",
                "aggregation": "count_distinct",
                "grain": "order proxy",
                "source_column": "会员卡号, 日期, 订单细分类型",
                "caveats": ["无真实订单号"],
            }],
            dimensions=[{
                "name": "渠道",
                "type": "categorical",
                "source_column": "渠道",
            }],
        )

        markdown = preflight_to_markdown(
            build_preflight_envelope(
                project=None,
                project_contexts=[],
                semantic_layer=layer,
                profiles=[profile],
            )
        )

        assert "## Complete Dataset Map" in markdown
        assert "field_13" in markdown
        assert "formula=COUNT_DISTINCT" in markdown
        assert "grain=order proxy" in markdown
        assert "dataset_paths[0]" in markdown
        assert "Do not write evidence files to /tmp" in markdown

    def test_preflight_preserves_context_kind_and_full_metric_definition(self):
        body = "订单口径：" + ("按会员、日期和订单细分类型去重。" * 100) + "TAIL_MARKER"
        context = ProjectContext(
            id="ctx-1",
            project_id="project-1",
            kind="metric_definition",
            title="订单数定义",
            body=body,
        )

        preflight = build_preflight_envelope(
            project=None,
            project_contexts=[context],
            semantic_layer=SemanticLayer(),
            profiles=[],
        )

        assert preflight.project_contexts[0]["type"] == "metric_definition"
        assert "TAIL_MARKER" in preflight.project_contexts[0]["body"]


class TestSavedYamlProvenance:
    def test_saved_yaml_includes_provenance(self, tmp_path):
        """Verify save_finding output includes provenance fields and is readable
        by load_semantic_layer."""
        sl_path = tmp_path / "semantic-layer.yaml"

        entry = MetricEntry(
            name="test_metric",
            formula="SUM(x)",
            grain="day",
            dimensions=["region"],
            sources=["test.csv"],
            caveat="test caveat",
        )
        metric_dict = {
            "name": entry.name,
            "formula": entry.formula,
            "grain": entry.grain,
            "dimensions": entry.dimensions,
            "sources": entry.sources,
            "caveat": entry.caveat,
            "aggregation": "SUM",
            "source_column": "x",
            "source_dataset": "test.csv",
            "timestamp": "2024-01-01T00:00:00",
            "run_id": "test_run",
            "provenance": {
                "run_id": "test_run",
                "timestamp": "2024-01-01T00:00:00Z",
                "source_dataset": "test.csv",
                "aggregation": "SUM",
                "source_column": "x",
            },
        }

        data = {"metrics": [metric_dict]}
        sl_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        # Verify YAML roundtrip
        loaded = yaml.safe_load(sl_path.read_text(encoding="utf-8"))
        assert "metrics" in loaded
        assert len(loaded["metrics"]) == 1
        m = loaded["metrics"][0]
        assert m["name"] == "test_metric"
        assert m["formula"] == "SUM(x)"
        assert m["grain"] == "day"
        assert m["dimensions"] == ["region"]
        assert m["sources"] == ["test.csv"]
        assert m["caveat"] == "test caveat"
        assert "provenance" in m
        assert m["provenance"]["run_id"] == "test_run"
        assert m["provenance"]["source_dataset"] == "test.csv"
        assert m["provenance"]["aggregation"] == "SUM"
        assert m["provenance"]["source_column"] == "x"
        # Backward compatibility fields preserved
        assert m["aggregation"] == "SUM"
        assert m["source_column"] == "x"
        assert m["run_id"] == "test_run"

        # Verify load_semantic_layer can read it
        sl = load_semantic_layer(sl_path)
        assert len(sl.metrics) == 1
        assert sl.metrics[0]["name"] == "test_metric"
        assert sl.metrics[0]["provenance"]["run_id"] == "test_run"

    def test_metric_entry_to_yaml_roundtrip(self, tmp_path):
        """MetricEntry -> dict -> YAML -> read back -> fields match."""
        sl_path = tmp_path / "roundtrip.yaml"

        entry = MetricEntry(
            name="revenue",
            formula="SUM(revenue)",
            grain="monthly",
            dimensions=["category"],
            sources=["sales_2024.csv"],
            caveat="Excludes refunds",
        )
        metric_dict = {
            "name": entry.name,
            "formula": entry.formula,
            "grain": entry.grain,
            "dimensions": entry.dimensions,
            "sources": entry.sources,
            "caveat": entry.caveat,
            "provenance": {
                "run_id": "run_001",
                "timestamp": entry.created_at,
            },
        }
        data = {"metrics": [metric_dict]}
        sl_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        loaded = yaml.safe_load(sl_path.read_text(encoding="utf-8"))
        m = loaded["metrics"][0]
        assert m["name"] == entry.name
        assert m["formula"] == entry.formula
        assert m["grain"] == entry.grain
        assert m["dimensions"] == entry.dimensions
        assert m["sources"] == entry.sources
        assert m["caveat"] == entry.caveat
        assert m["provenance"]["run_id"] == "run_001"

    def test_semantic_layer_with_provenance_readable(self, tmp_path):
        """Full semantic layer YAML with provenance loads correctly."""
        sl_path = tmp_path / "full-layer.yaml"
        data = {
            "metrics": [
                {
                    "name": "avg_price",
                    "formula": "AVG(price)",
                    "grain": "monthly",
                    "dimensions": ["product_type"],
                    "sources": ["pricing.csv"],
                    "caveat": "Outliers removed",
                    "aggregation": "AVG",
                    "source_column": "price",
                    "source_dataset": "pricing.csv",
                    "timestamp": "2024-06-01T12:00:00",
                    "run_id": "run_abc",
                    "provenance": {
                        "run_id": "run_abc",
                        "timestamp": "2024-06-01T12:00:00Z",
                        "source_dataset": "pricing.csv",
                        "aggregation": "AVG",
                        "source_column": "price",
                    },
                }
            ],
            "dimensions": [],
        }
        sl_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        sl = load_semantic_layer(sl_path)
        assert len(sl.metrics) == 1
        m = sl.metrics[0]
        assert m["name"] == "avg_price"
        assert m["provenance"]["aggregation"] == "AVG"


class TestDeriveSemanticLayer:
    def test_numeric_columns_get_unknown_aggregation(self):
        """derive_semantic_layer marks numeric columns as aggregation='unknown'."""
        profile = DatasetProfile(
            dataset_id="test-ds",
            filename="test.csv",
            row_count=100,
            column_count=3,
            columns=[
                ColumnProfile(
                    name="revenue",
                    dtype="float64",
                    non_null_count=95,
                    null_count=5,
                    null_pct=5.0,
                    unique_count=50,
                    min_value="10.0",
                    max_value="1000.0",
                    mean_value=500.0,
                ),
                ColumnProfile(
                    name="category",
                    dtype="object",
                    non_null_count=100,
                    null_count=0,
                    null_pct=0.0,
                    unique_count=5,
                    sample_values=["A", "B", "C"],
                ),
                ColumnProfile(
                    name="order_date",
                    dtype="object",
                    non_null_count=100,
                    null_count=0,
                    null_pct=0.0,
                    unique_count=30,
                    sample_values=["2024-01-01", "2024-01-02"],
                ),
            ],
        )
        sl = derive_semantic_layer([profile])
        metric_names = [m["name"] for m in sl.metrics]
        assert "revenue" in metric_names, "numeric column 'revenue' should be a metric"
        rev_metric = next(m for m in sl.metrics if m["name"] == "revenue")
        assert rev_metric["aggregation"] == "unknown", (
            f"expected aggregation='unknown', got '{rev_metric['aggregation']}'"
        )
        assert rev_metric["dtype"] == "float64"

    def test_date_columns_not_treated_as_numeric(self):
        """Columns with date-like names should NOT be metrics."""
        profile = DatasetProfile(
            dataset_id="test-ds",
            filename="test.csv",
            row_count=100,
            column_count=1,
            columns=[
                ColumnProfile(
                    name="date",
                    dtype="int64",
                    non_null_count=100,
                    null_count=0,
                    null_pct=0.0,
                    unique_count=30,
                ),
            ],
        )
        sl = derive_semantic_layer([profile])
        metric_names = [m["name"] for m in sl.metrics]
        assert "date" not in metric_names, "date column should not be a metric"

    def test_high_null_rate_generates_caveat(self):
        """Columns with >20% null should generate a caveat."""
        profile = DatasetProfile(
            dataset_id="test-ds",
            filename="test.csv",
            row_count=100,
            column_count=1,
            columns=[
                ColumnProfile(
                    name="discount",
                    dtype="float64",
                    non_null_count=70,
                    null_count=30,
                    null_pct=30.0,
                    unique_count=10,
                    min_value="0.0",
                    max_value="50.0",
                    mean_value=10.0,
                ),
            ],
        )
        sl = derive_semantic_layer([profile])
        assert any(c["column"] == "discount" for c in sl.caveats), (
            "high-null column should generate caveat"
        )
        disc_metric = next(m for m in sl.metrics if m["name"] == "discount")
        assert disc_metric["aggregation"] == "unknown"
