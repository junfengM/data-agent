"""Preflight context: dataset profiling helpers."""
from app.models.schemas import DatasetProfile


def profile_table_data(profiles: list[DatasetProfile]) -> dict:
    rows: list[dict] = []
    for profile in profiles:
        for column in profile.columns:
            rows.append({
                "dataset": profile.filename,
                "column": column.name,
                "dtype": column.dtype,
                "non_null_count": column.non_null_count,
                "null_count": column.null_count,
                "null_pct": column.null_pct,
                "unique_count": column.unique_count,
            })
    return {
        "columns": [
            {"key": "dataset", "label": "数据集"},
            {"key": "column", "label": "字段"},
            {"key": "dtype", "label": "类型"},
            {"key": "non_null_count", "label": "非空"},
            {"key": "null_count", "label": "空值"},
            {"key": "null_pct", "label": "空值率"},
            {"key": "unique_count", "label": "唯一值"},
        ],
        "rows": rows,
    }


def profile_chart_data(profiles: list[DatasetProfile]) -> dict | None:
    if not profiles:
        return None
    profile = profiles[0]
    rows = [
        {"label": col.name, "value": col.non_null_count, "secondary_value": col.null_count}
        for col in profile.columns[:10]
    ]
    if not rows:
        return None
    return {
        "chart_type": "bar",
        "x": "label",
        "y": "value",
        "secondary_y": "secondary_value",
        "unit": "rows",
        "rows": rows,
        "source": profile.filename,
        "description": "每个字段的非空行数，辅助显示空值数量。",
    }
