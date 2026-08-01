from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import get_settings
from app.models.schemas import ColumnProfile, DatasetProfile, DatasetRecord


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_PROFILE_VALUE_CHARS = 200
_PROFILE_CACHE_VERSION = "v1"
_profile_cache: dict[tuple[Any, ...], dict[str, Any]] = {}


def clear_profile_cache() -> None:
    """Clear the in-memory dataset profile cache (used by tests/ops)."""
    _profile_cache.clear()


def _file_fingerprint(path: Path) -> tuple[Any, ...] | None:
    try:
        stat = path.stat()
        return (
            str(path.resolve()),
            stat.st_size,
            stat.st_mtime_ns,
            _PROFILE_CACHE_VERSION,
        )
    except OSError:
        return None


def profile_dataset(dataset: DatasetRecord, max_sample_values: int = 5) -> DatasetProfile:
    key = _file_fingerprint(dataset.path)
    if key is not None and key in _profile_cache:
        cached = _profile_cache[key]
        return DatasetProfile(
            dataset_id=dataset.id,
            filename=dataset.filename,
            row_count=cached["row_count"],
            column_count=cached["column_count"],
            columns=cached["columns"],
            warnings=cached["warnings"],
            sampled=cached["sampled"],
        )

    frame, warnings, sampled = load_dataframe(dataset.path)
    columns = [
        profile_column(name, frame[name], max_sample_values=max_sample_values)
        for name in frame.columns
    ]
    profile = DatasetProfile(
        dataset_id=dataset.id,
        filename=dataset.filename,
        row_count=_full_row_count(dataset.path, frame, sampled),
        column_count=int(len(frame.columns)),
        columns=columns,
        warnings=warnings,
        sampled=sampled,
    )
    if key is not None:
        _profile_cache[key] = {
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "columns": profile.columns,
            "warnings": profile.warnings,
            "sampled": profile.sampled,
        }
    return profile


def load_dataframe(path: Path) -> tuple[pd.DataFrame, list[str], bool]:
    suffix = path.suffix.lower()
    warnings: list[str] = []
    sampled = False
    settings = get_settings()
    if suffix == ".csv":
        total_rows = _count_csv_data_rows(path)
        threshold = settings.profile_sampling_threshold_rows
        if total_rows is not None and total_rows > threshold:
            frame = pd.read_csv(path, nrows=settings.profile_sampling_max_rows)
            sampled = True
            warnings.append(
                f"数据集超过 {threshold} 行，画像基于前 "
                f"{settings.profile_sampling_max_rows} 行采样。"
            )
        else:
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
    return frame, warnings, sampled


def _count_csv_data_rows(path: Path) -> int | None:
    """Count CSV data rows without materializing the frame.

    Uses DuckDB's streaming CSV reader; falls back to None (no sampling) if the
    file cannot be read that way.
    """
    try:
        import duckdb

        with duckdb.connect() as conn:
            row = conn.execute(
                "select count(*) from read_csv_auto(?, header=true, sample_size=-1)",
                [str(path)],
            ).fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None


def _full_row_count(path: Path, frame: pd.DataFrame, sampled: bool) -> int:
    if not sampled:
        return int(len(frame))
    count = _count_csv_data_rows(path)
    if count is not None:
        return count
    return int(len(frame))


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
