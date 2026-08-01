import os
import subprocess
import sys

import pytest

from app.tools.execution import (
    LocalDevRunner,
    _normalize_mode,
    run_analysis_code,
)
from app.core.settings import get_settings


duckdb = pytest.importorskip("duckdb")


@pytest.fixture
def run_dir(tmp_path):
    return tmp_path / "run"


def test_local_execution_uses_sys_executable(run_dir):
    code = "import sys; print(sys.executable)"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    assert result.returncode == 0
    assert sys.executable in result.stdout


def test_local_execution_scrubs_env(run_dir):
    os.environ["TEST_SECRET_KEY"] = "should_not_appear"
    try:
        code = "import os; print(os.environ.get('TEST_SECRET_KEY', 'NOT_FOUND'))"
        result = run_analysis_code(
            code=code,
            run_dir=run_dir,
            dataset_paths=[],
            generated_code_execution="local-dev",
        )
        assert result.returncode == 0
        assert "should_not_appear" not in result.stdout
        assert "NOT_FOUND" in result.stdout
    finally:
        del os.environ["TEST_SECRET_KEY"]


def test_local_execution_rewrites_home_and_removes_pythonpath(run_dir):
    os.environ["PYTHONPATH"] = "should_not_appear"
    try:
        code = "import os; print(os.environ.get('PYTHONPATH', 'NO_PYTHONPATH')); print(os.environ['HOME'])"
        result = run_analysis_code(
            code=code,
            run_dir=run_dir,
            dataset_paths=[],
            generated_code_execution="local-dev",
        )
        assert result.returncode == 0
        assert "should_not_appear" not in result.stdout
        assert "NO_PYTHONPATH" in result.stdout
        assert str(run_dir / "_home") in result.stdout
    finally:
        del os.environ["PYTHONPATH"]


def test_local_execution_csv_becomes_table(run_dir):
    code = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6]})\n"
        "df.to_csv('output.csv', index=False)\n"
    )
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    assert result.returncode == 0
    assert len(result.tables) == 1
    assert result.tables[0]["name"] == "output"
    assert result.tables[0]["rows"] == 3
    assert "x" in result.tables[0]["columns"]
    assert "y" in result.tables[0]["columns"]


def test_local_execution_collects_nested_outputs(run_dir):
    code = (
        "from pathlib import Path\n"
        "import pandas as pd\n"
        "Path('outputs/charts').mkdir(parents=True)\n"
        "pd.DataFrame({'x': [1]}).to_csv('outputs/table.csv', index=False)\n"
        "Path('outputs/charts/plot.png').write_bytes(b'png')\n"
    )
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    assert result.returncode == 0
    assert [table["name"] for table in result.tables] == ["table"]
    assert [chart["name"] for chart in result.charts] == ["plot"]
    assert result.charts[0]["render_mode"] == "file"
    assert "outputs/charts/plot.png" in result.charts[0]["asset_path"]


def test_local_execution_timeout_returns_structured_result(run_dir):
    code = "import time\ntime.sleep(5)"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        timeout_seconds=1,
        generated_code_execution="local-dev",
    )
    assert result.returncode == 124
    assert "timed out" in result.stderr.lower()


def test_local_execution_applies_default_timeout(run_dir, monkeypatch):
    observed = {}

    def fake_run(self, script_path, run_dir_arg, timeout_seconds):
        observed["timeout_seconds"] = timeout_seconds
        return subprocess.CompletedProcess(
            args=[sys.executable, str(script_path)],
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(LocalDevRunner, "run", fake_run)

    result = run_analysis_code(
        code="print('ok')",
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 0
    assert observed["timeout_seconds"] == get_settings().analysis_execution_timeout_seconds


def test_local_execution_blocks_subprocess_import_before_run_dir_creation(run_dir):
    result = run_analysis_code(
        code="import subprocess\nsubprocess.run(['echo', 'nope'])",
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 2
    assert "blocked risky api" in result.stderr.lower()
    assert "subprocess" in result.stderr.lower()
    assert not run_dir.exists()


def test_local_execution_blocks_os_system_call_before_run_dir_creation(run_dir):
    result = run_analysis_code(
        code="import os\nos.system('echo nope')",
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 2
    assert "blocked risky api" in result.stderr.lower()
    assert "os.system" in result.stderr.lower()
    assert not run_dir.exists()


def test_dataset_paths_are_actual_paths_and_variables_remain_available(run_dir, tmp_path):
    dataset = tmp_path / "84a56d7238054901acc8153c817016c1.csv"
    dataset.write_text("x\n1\n", encoding="utf-8")
    code = (
        "import pandas as pd\n"
        "assert dataset_paths[0].endswith('.csv')\n"
        "assert dataset_paths[0] == dataset_vars[dataset_path_variables[0]]\n"
        "df = pd.read_csv(dataset_paths[0])\n"
        "print(df['x'].sum())\n"
    )

    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[dataset],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 0
    assert result.stdout == "1"


def test_disabled_execution_blocks(run_dir):
    code = "print('should not run')"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="disabled",
    )
    assert result.returncode == 2
    assert "disabled" in result.stderr.lower()
    assert result.stdout == ""
    assert result.tables == []
    assert result.charts == []


def test_disabled_execution_does_not_create_run_dir(run_dir):
    assert not run_dir.exists()
    code = "print('test')"
    run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="disabled",
    )
    assert not run_dir.exists()


def test_local_execution_creates_run_dir(run_dir):
    assert not run_dir.exists()
    code = "print('test')"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    assert result.returncode == 0
    assert run_dir.exists()


# ── new tests for runner abstraction ──


def test_legacy_local_mode_still_works(run_dir):
    code = "print('hello from legacy local')"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local",
    )
    assert result.returncode == 0
    assert "hello from legacy local" in result.stdout


def test_sandbox_mode_without_backend_returns_clear_error(run_dir):
    code = "print('should not run')"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="sandbox",
    )
    assert result.returncode == 2
    assert "no sandbox backend" in result.stderr.lower()
    assert result.tables == []
    assert result.charts == []


def test_unknown_mode_defaults_to_disabled(run_dir):
    code = "print('should not run')"
    result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="garbage",
    )
    assert result.returncode == 2
    assert "disabled" in result.stderr.lower()


class TestNormalizeMode:
    def test_local_maps_to_local_dev(self):
        assert _normalize_mode("local") == "local-dev"

    def test_local_dev_passes_through(self):
        assert _normalize_mode("local-dev") == "local-dev"

    def test_disabled_passes_through(self):
        assert _normalize_mode("disabled") == "disabled"

    def test_sandbox_passes_through(self):
        assert _normalize_mode("sandbox") == "sandbox"

    def test_unknown_defaults_to_disabled(self):
        assert _normalize_mode("nonsense") == "disabled"


class TestGrowthRateHelpers:
    def test_safe_growth_rate_normal(self):
        from app.tools.execution import safe_growth_rate
        result = safe_growth_rate(150, 100)
        assert result == 0.5

    def test_safe_growth_rate_zero_previous(self):
        from app.tools.execution import safe_growth_rate
        result = safe_growth_rate(100, 0)
        assert result is None

    def test_safe_growth_rate_none_previous(self):
        from app.tools.execution import safe_growth_rate
        result = safe_growth_rate(100, None)
        assert result is None

    def test_safe_growth_rate_negative(self):
        from app.tools.execution import safe_growth_rate
        result = safe_growth_rate(50, 100)
        assert result == -0.5

    def test_format_growth_rate_normal(self):
        from app.tools.execution import format_growth_rate
        result = format_growth_rate(0.156)
        assert "15.6%" in result

    def test_format_growth_rate_new_appearance(self):
        from app.tools.execution import format_growth_rate
        result = format_growth_rate(None, current=100, previous=0)
        assert result in ("新出现", "N/A", "前期无销售，不计算增长率")

    def test_format_growth_rate_na(self):
        from app.tools.execution import format_growth_rate
        result = format_growth_rate(None)
        assert result == "N/A"

    def test_zero_baseline_growth_not_inf(self):
        from app.tools.execution import format_growth_rate, safe_growth_rate
        rate = safe_growth_rate(100, 0)
        assert rate is None
        formatted = format_growth_rate(rate, current=100, previous=0)
        assert "inf" not in formatted.lower()
        assert "Infinity" not in formatted


def test_planner_tools_do_not_include_evaluate_attempt():
    from app.agent.planner import Planner
    tools = Planner._tool_definitions()
    names = [t["function"]["name"] for t in tools]
    assert "evaluate_attempt" not in names
    assert "execute_code" in names
    assert "list_skills" in names
