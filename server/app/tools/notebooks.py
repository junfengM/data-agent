from pathlib import Path

import nbformat

from app.models.schemas import DatasetProfile


def write_profile_notebook(
    artifacts_dir: Path,
    run_id: str,
    title: str,
    question: str,
    dataset_paths: list[Path],
    profiles: list[DatasetProfile],
) -> Path:
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "analysis-notebook.ipynb"

    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell(f"# {title}\n\n**Question:** {question}"),
        nbformat.v4.new_markdown_cell("## Dataset Profiles\n\n" + _profile_summary(profiles)),
        nbformat.v4.new_code_cell(_starter_code(dataset_paths)),
    ]
    nbformat.write(notebook, path)
    return path


def _profile_summary(profiles: list[DatasetProfile]) -> str:
    if not profiles:
        return "No dataset profiles were generated."
    lines: list[str] = []
    for profile in profiles:
        lines.append(f"- `{profile.filename}`: {profile.row_count} rows, {profile.column_count} columns")
    return "\n".join(lines)


def _starter_code(dataset_paths: list[Path]) -> str:
    paths = [str(path) for path in dataset_paths]
    return "\n".join(
        [
            "import pandas as pd",
            "",
            f"dataset_paths = {paths!r}",
            "frames = {}",
            "for path in dataset_paths:",
            "    if path.endswith('.csv'):",
            "        frames[path] = pd.read_csv(path)",
            "    else:",
            "        frames[path] = pd.read_excel(path)",
            "",
            "for path, frame in frames.items():",
            "    print(path, frame.shape)",
            "    display(frame.head())",
        ]
    )

