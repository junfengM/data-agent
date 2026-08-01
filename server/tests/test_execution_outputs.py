
from unittest.mock import MagicMock

from app.tools.execution import _collect_output_candidates


def test_collect_output_candidates_skips_symlinks_and_inputs(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    external = tmp_path / "external.csv"
    external.write_text("id\n1\n", encoding="utf-8")

    good = run_dir / "outputs" / "table.csv"
    good.parent.mkdir()
    good.write_text("id\n1\n", encoding="utf-8")

    datasets_dir = run_dir / "datasets"
    datasets_dir.mkdir()
    copied_input = datasets_dir / "input.csv"
    copied_input.write_text("id\n2\n", encoding="utf-8")

    symlink = run_dir / "leaked.csv"
    symlink.symlink_to(external)

    assert _collect_output_candidates(run_dir) == {good.resolve()}


def test_collect_output_candidates_skips_oversized_files(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    small = run_dir / "small.csv"
    large = run_dir / "large.csv"
    small.write_text("id\n1\n", encoding="utf-8")
    large.write_text("id\n123456\n", encoding="utf-8")

    mock_settings = MagicMock()
    mock_settings.analysis_max_output_bytes = small.stat().st_size
    mock_settings.analysis_max_output_files = 999
    monkeypatch.setattr("app.tools.execution.get_settings", lambda: mock_settings)

    assert _collect_output_candidates(run_dir) == {small.resolve()}
