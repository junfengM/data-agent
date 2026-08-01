from pathlib import Path
from typing import Any

import pandas as pd

from app.models.schemas import ColumnProfile, DatasetProfile, DatasetRecord


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_PROFILE_VALUE_CHARS = 200


def profile_dataset(dataset: DatasetRecord, max_sample_values: int = 5) -> DatasetProfile:
    frame, warnings = load_dataframe(dataset.path)
    columns = [
        profile_column(name, frame[name], max_sample_values=max_sample_values)
        for name in frame.columns
    ]
    return DatasetProfile(
        dataset_id=dataset.id,
        filename=dataset.filename,
        row_count=int(len(frame)),
        column_count=int(len(frame.columns)),
        columns=columns,
        warnings=warnings,
    )


def load_dataframe(path: Path) -> tuple[pd.DataFrame, list[str]]:
    suffix = path.suffix.lower()
    warnings: list[str] = []
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
        warnings.append("Excel import currently reads the first sheet only.")
    else:
        raise ValueError(f"Unsupported dataset type: {suffix}. Supported types: {sorted(SUPPORTED_EXTENSIONS)}")

    if frame.empty:
        warnings.append("Dataset has no rows.")
    if len(frame.columns) == 0:
        warnings.append("Dataset has no columns.")
    return frame, warnings


def profile_column(name: str, series: pd.Series, max_sample_values: int) -> ColumnProfile:
    non_null = series.dropna()
    numeric = pd.to_numeric(non_null, errors="coerce")
    numeric_non_null = numeric.dropna()
    min_value: str | None = None
    max_value: str | None = None
    mean_value: float | None = None

    if not numeric_non_null.empty and len(numeric_non_null) == len(non_null):
        min_value = _safe_string(numeric_non_null.min())
        max_value = _safe_string(numeric_non_null.max())
        mean_value = float(numeric_non_null.mean())
    elif not non_null.empty:
        min_value = _safe_string(non_null.min())
        max_value = _safe_string(non_null.max())

    return ColumnProfile(
        name=str(name),
        dtype=str(series.dtype),
        non_null_count=int(series.notna().sum()),
        null_count=int(series.isna().sum()),
        null_pct=round(float(series.isna().mean() * 100), 2),
        unique_count=int(series.nunique(dropna=True)),
        sample_values=[_safe_string(value) for value in non_null.drop_duplicates().head(max_sample_values)],
        min_value=min_value,
        max_value=max_value,
        mean_value=round(mean_value, 4) if mean_value is not None else None,
    )


def _safe_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = " ".join(text.split())
    if len(text) > MAX_PROFILE_VALUE_CHARS:
        return text[:MAX_PROFILE_VALUE_CHARS - 1] + "…"
    return text
