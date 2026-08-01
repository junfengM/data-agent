"""Chart manifest helpers (extracted from artifact_manifest.py)."""
from typing import Any

from app.models.schemas import ChartEncoding, ChartEncodings, ManifestChart
from app.agent.artifact_manifest_helpers import _tokenize


def _chart_score(block_text: str, chart: ManifestChart, chart_specs: list[dict] | None) -> int:
    text = block_text.lower()
    score = 0
    spec = next((s for s in chart_specs or [] if str(s.get("name", "")).lower() == chart.title.lower()), {})
    haystacks = [chart.title, chart.description or "", str(spec.get("title", "")), str(spec.get("intent", ""))]
    for hay in haystacks:
        if hay and hay.lower() in text:
            score += 8
    score += len(_tokenize(text) & _tokenize(" ".join(haystacks)))
    for field in [spec.get("x_field"), *spec.get("y_fields", [])] if spec else []:
        if field and str(field).lower() in text:
            score += 2
    return score


def _chart_spec_for(chart_name: str, chart_specs: list[dict] | None) -> dict[str, Any]:
    """Find a normalized chart spec for a produced chart by name or title."""
    name_lower = chart_name.lower()
    for spec in chart_specs or []:
        spec_name = str(spec.get("name") or "").lower()
        spec_title = str(spec.get("title") or "").lower()
        if spec_name == name_lower or spec_title == name_lower:
            return spec
    return {}


def _merge_chart_info_and_spec(chart_info: dict, chart_spec: dict, chart_type: str) -> dict[str, Any]:
    """Merge runtime chart output with chart_specs metadata for encoding inference."""
    merged = dict(chart_spec or {})
    merged.update(chart_info or {})
    merged["type"] = chart_type
    if chart_spec.get("x_field") and not (merged.get("x") or merged.get("x_axis")):
        merged["x_axis"] = chart_spec["x_field"]
    y_fields = chart_spec.get("y_fields")
    if isinstance(y_fields, list) and y_fields:
        merged.setdefault("y_fields", y_fields)
        if not (merged.get("y") or merged.get("y_axis")):
            merged["y_axis"] = y_fields[0]
    return merged


def _direct_rows(value: Any) -> list[dict[str, Any]]:
    """Return preview rows when an artifact already carries tabular data."""
    if isinstance(value, list) and all(isinstance(row, dict) for row in value[:5]):
        return value
    return []


def _chart_required_fields(chart: ManifestChart, chart_spec: dict[str, Any] | None = None) -> set[str]:
    fields: set[str] = set()
    if chart.encodings.x and chart.encodings.x.field:
        fields.add(chart.encodings.x.field)
    if chart.encodings.y:
        if chart.encodings.y.field:
            fields.add(chart.encodings.y.field)
        for field in chart.encodings.y.fields or []:
            if field:
                fields.add(field)
    if chart_spec:
        if chart_spec.get("x_field"):
            fields.add(str(chart_spec["x_field"]))
        for field in chart_spec.get("y_fields") or []:
            if field:
                fields.add(str(field))
    return fields


def _rows_have_fields(rows: list[dict[str, Any]], required_fields: set[str]) -> bool:
    if not rows or not required_fields:
        return False
    available = set(rows[0].keys())
    return required_fields.issubset(available)


def _find_rows_for_chart(
    chart: ManifestChart,
    chart_info: dict[str, Any] | None,
    chart_spec: dict[str, Any] | None,
    all_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chart_info = chart_info or {}
    direct = _direct_rows(chart_info.get("data")) or _direct_rows(chart_info.get("preview")) or _direct_rows(chart_info.get("rows"))
    required = _chart_required_fields(chart, chart_spec)
    if direct and (not required or _rows_have_fields(direct, required)):
        return direct
    if not required:
        return []
    for table_info in all_tables:
        rows = _direct_rows(table_info.get("preview")) or _direct_rows(table_info.get("rows")) or _direct_rows(table_info.get("data"))
        if _rows_have_fields(rows, required):
            return rows
    return []


def _promote_native_chart_if_possible(
    chart: ManifestChart,
    rows: list[dict[str, Any]],
    chart_info: dict[str, Any] | None,
) -> None:
    """Use native chart rendering when a file chart has complete data bindings.

    LLMs still often save Plotly/PNG artifacts.  If the same step also produced
    rows and encodings, the visual report should render the chart as a native
    component while keeping the file asset as optional source evidence.
    """
    if chart.render_mode != "file":
        return
    required = _chart_required_fields(chart)
    if not _rows_have_fields(rows, required):
        return
    if not chart.encodings.x or not chart.encodings.y:
        return
    chart.render_mode = "vega"
    if chart_info:
        chart.description = chart.description or chart_info.get("description")


def normalize_chart_type(raw_type: str) -> str:
    type_map = {
        "png": "bar", "jpg": "bar", "jpeg": "bar", "svg": "bar",
        "html": "bar", "plotly": "bar",
        "bar": "bar", "horizontalBar": "horizontalBar",
        "line": "line", "area": "area",
        "scatter": "scatter", "pie": "pie",
        "stackedBar": "stackedBar", "stackedBar100": "stackedBar100",
        "stackedArea": "stackedArea",
        "horizontalStackedBar": "horizontalStackedBar",
        "horizontalStackedBar100": "horizontalStackedBar100",
        "histogram": "histogram", "heatmap": "heatmap",
        "leaderboard": "leaderboard", "sparkline": "sparkline",
        "funnel": "funnel", "waterfall": "waterfall", "boxPlot": "boxPlot",
    }
    return type_map.get(raw_type, "bar")


def infer_chart_encodings(chart_info: dict) -> ChartEncodings:
    x_field = chart_info.get("x") or chart_info.get("x_axis") or chart_info.get("x_field")
    y_fields = chart_info.get("y_fields") if isinstance(chart_info.get("y_fields"), list) else []
    y_field = chart_info.get("y") or chart_info.get("y_axis") or (y_fields[0] if y_fields else None)
    chart_type = chart_info.get("type", "bar")

    x_enc = ChartEncoding(field=x_field) if x_field else None
    y_enc = ChartEncoding(field=y_field) if y_field else None
    if y_enc and y_fields:
        y_enc.fields = [str(field) for field in y_fields if field]
    y_unit = chart_info.get("unit")
    if y_enc and y_unit:
        y_enc.unit = y_unit
    y_enc_label = chart_info.get("y_axis_title")
    if y_enc and y_enc_label:
        y_enc.label = y_enc_label

    enc = ChartEncodings(x=x_enc, y=y_enc)

    color_field = chart_info.get("color") or chart_info.get("color_field")
    if color_field:
        enc.color = ChartEncoding(field=color_field)

    facet_field = chart_info.get("facet") or chart_info.get("facet_field")
    if facet_field:
        enc.facet = ChartEncoding(field=facet_field)

    label_field = chart_info.get("label") or chart_info.get("label_field")
    if label_field:
        enc.label = ChartEncoding(field=label_field)

    secondary_field = chart_info.get("secondary_value") or chart_info.get("secondary_y")
    if secondary_field:
        if y_enc:
            y_enc.fields = [y_field, secondary_field] if y_field else [secondary_field]

    if chart_type == "scatter":
        size_field = chart_info.get("size")
        if size_field:
            enc.size = ChartEncoding(field=size_field)

    if chart_type == "boxPlot":
        quartile_fields = chart_info.get("quartiles")
        if quartile_fields and isinstance(quartile_fields, list):
            if y_enc:
                y_enc.fields = y_enc.fields or [y_field] if y_field else []
                y_enc.fields.extend(quartile_fields)
    if chart_type == "heatmap":
        matrix_field = chart_info.get("matrix") or chart_info.get("matrix_field")
        if matrix_field:
            if y_enc:
                y_enc.fields = y_enc.fields or [y_field] if y_field else []
                y_enc.fields.append(matrix_field)

    return enc
