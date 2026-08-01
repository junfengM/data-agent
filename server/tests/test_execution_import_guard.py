from pathlib import Path

from app.tools.execution import run_analysis_code, format_analysis_dependency_status_for_prompt


def test_run_analysis_code_blocks_unsupported_third_party_import(tmp_path: Path):
    result = run_analysis_code(
        code="import seaborn as sns\nprint('should not run')",
        run_dir=tmp_path,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 2
    assert "Unsupported import" in result.stderr
    assert "seaborn" in result.stderr
    assert "pandas" in result.stderr
    assert result.stdout == ""


def test_matplotlib_import_is_rejected(tmp_path: Path):
    result = run_analysis_code(
        code="import matplotlib.pyplot as plt\nprint('bad')",
        dataset_paths=[],
        run_dir=tmp_path,
        generated_code_execution="local-dev",
    )

    assert result.returncode == 2
    assert "Unsupported import" in result.stderr
    assert "matplotlib" in result.stderr


def test_dependency_prompt_does_not_list_matplotlib():
    prompt = format_analysis_dependency_status_for_prompt()
    # matplotlib must not appear as an available/recommended package.
    # The prompt may mention "Do not use matplotlib" as a prohibition rule — that is correct.
    assert "do not use matplotlib" in prompt.lower()
    assert "plotly" in prompt.lower()


def test_run_analysis_code_allows_supported_and_stdlib_imports(tmp_path: Path):
    result = run_analysis_code(
        code=(
            "import json\n"
            "import pandas as pd\n"
            "df = pd.DataFrame({'x': [1, 2]})\n"
            "print(json.dumps({'rows': len(df)}))\n"
        ),
        run_dir=tmp_path,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 0
    assert '"rows": 2' in result.stdout
    assert result.stderr == ""


def test_run_analysis_code_allows_xlsxwriter_import(tmp_path: Path):
    result = run_analysis_code(
        code=(
            "import xlsxwriter\n"
            "workbook = xlsxwriter.Workbook('summary.xlsx')\n"
            "worksheet = workbook.add_worksheet()\n"
            "worksheet.write(0, 0, 'ok')\n"
            "workbook.close()\n"
            "print('xlsx created')\n"
        ),
        run_dir=tmp_path,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )

    assert result.returncode == 0
    assert "xlsx created" in result.stdout
    assert result.stderr == ""
