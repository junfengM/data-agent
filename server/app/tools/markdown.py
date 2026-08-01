from app.models.schemas import DatasetProfile


def profiles_to_markdown(profiles: list[DatasetProfile]) -> str:
    if not profiles:
        return "No dataset profiles were generated."

    sections: list[str] = []
    for profile in profiles:
        sections.extend(
            [
                f"### {profile.filename}",
                "",
                f"- Dataset ID: `{profile.dataset_id}`",
                f"- Rows: {profile.row_count}",
                f"- Columns: {profile.column_count}",
                "",
            ]
        )
        if profile.warnings:
            sections.append("Warnings:")
            sections.extend([f"- {warning}" for warning in profile.warnings])
            sections.append("")

        sections.extend(
            [
                "| Column | Type | Non-null | Null % | Unique | Min | Max | Mean | Samples |",
                "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
            ]
        )
        for column in profile.columns:
            samples = ", ".join(column.sample_values)
            sections.append(
                "| "
                + " | ".join(
                    [
                        _cell(column.name),
                        _cell(column.dtype),
                        str(column.non_null_count),
                        f"{column.null_pct:.2f}",
                        str(column.unique_count),
                        _cell(column.min_value),
                        _cell(column.max_value),
                        "" if column.mean_value is None else f"{column.mean_value:.4f}",
                        _cell(samples),
                    ]
                )
                + " |"
            )
        sections.append("")
    return "\n".join(sections)


def _cell(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")

