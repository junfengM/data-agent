from __future__ import annotations

from app.agent.planner_bridge import (
    _compact_step_payload_for_llm,
    _compact_step_table_for_llm,
)
from app.core.settings import get_settings

_limits = get_settings()


def test_compact_success_payload_omits_full_code():
    payload = {
        "name": "step1",
        "description": "desc",
        "code": "print('hello')\n" * 1000,
        "returncode": 0,
        "status": "completed",
        "stdout": "sales=123\nratio=45%",
        "stderr": "",
        "tables": [],
        "charts": [],
    }

    compact = _compact_step_payload_for_llm(payload)

    assert "code" not in compact
    assert compact["code_ref"] == "step1"
    assert compact["code_chars"] == len(payload["code"])
    assert "stdout_excerpt" in compact
    assert "stdout" in compact
    assert compact["stdout"] == compact["stdout_excerpt"]


def test_compact_failed_payload_keeps_error_context():
    payload = {
        "name": "bad_step",
        "description": "desc",
        "code": "x = 1\n" * 1000,
        "returncode": 1,
        "status": "failed",
        "stdout": "",
        "stderr": "Traceback...\nNameError: x",
        "tables": [],
        "charts": [],
    }

    compact = _compact_step_payload_for_llm(payload)

    assert compact["status"] == "failed"
    assert "code" not in compact
    assert "code_excerpt" in compact
    assert "NameError" in compact["stderr"]
    assert compact["code_excerpt_truncated"] is True


def test_compact_wide_table_omits_preview():
    table = {
        "name": "wide_matrix",
        "rows": 7,
        "columns": [f"col_{i}" for i in range(100)],
        "preview": [{f"col_{i}": i for i in range(100)} for _ in range(10)],
        "path": "wide_matrix.csv",
    }

    compact = _compact_step_table_for_llm(table)

    assert compact["columns_count"] == 100
    assert compact["preview"] == []
    assert compact["preview_omitted"] is True
    assert len(compact["columns_sample"]) <= _limits.llm_wide_table_column_sample
    assert "omission_reason" in compact
    assert "columns" in compact
    assert compact["columns"] == compact["columns_sample"]


def test_compact_narrow_table_limits_rows_and_columns():
    table = {
        "name": "monthly",
        "rows": 20,
        "columns": [f"col_{i}" for i in range(20)],
        "preview": [{f"col_{i}": i for i in range(20)} for _ in range(10)],
        "path": "monthly.csv",
    }

    compact = _compact_step_table_for_llm(table)

    assert len(compact["preview"]) <= _limits.llm_table_preview_rows
    assert len(compact["columns"]) <= _limits.llm_table_preview_columns
    assert compact["preview_omitted"] is False
    assert "columns" in compact
    assert "preview_rows" in compact
    assert "preview_columns" in compact


def test_compact_stdout_prioritizes_important_lines():
    payload = {
        "name": "step1",
        "description": "desc",
        "code": "print('x')",
        "returncode": 0,
        "status": "completed",
        "stdout": "reading file\nprocessing\ndone\nsales=123\nratio=45%\nmean=3.14: ok\n",
        "stderr": "",
        "tables": [],
        "charts": [],
    }

    compact = _compact_step_payload_for_llm(payload)

    assert "sales=123" in compact["stdout"]
    assert "ratio=45%" in compact["stdout"]


def test_compact_failed_step_tables_charts_marked_partial():
    payload = {
        "name": "fail_step",
        "description": "desc",
        "code": "raise",
        "returncode": 1,
        "status": "failed",
        "stdout": "",
        "stderr": "error",
        "tables": [
            {
                "name": "t1",
                "rows": 5,
                "columns": ["a", "b"],
                "preview": [{"a": 1, "b": 2}],
                "path": "t1.csv",
            }
        ],
        "charts": [
            {"name": "c1", "type": "html", "path": "c1.html"}
        ],
    }

    compact = _compact_step_payload_for_llm(payload)

    assert compact["tables"][0]["partial"] is True
    assert compact["charts"][0]["partial"] is True


def test_compact_success_step_stderr_empty():
    payload = {
        "name": "ok_step",
        "description": "desc",
        "code": "pass",
        "returncode": 0,
        "status": "completed",
        "stdout": "done",
        "stderr": "some warning",
        "tables": [],
        "charts": [],
    }

    compact = _compact_step_payload_for_llm(payload)

    assert compact["stderr"] == ""


def test_compact_stdout_respects_max_lines_from_settings():
    from app.agent.planner_bridge import _compact_stdout
    lines = [f"line_{i}: value={i}" for i in range(200)]
    stdout = "\n".join(lines)

    result = _compact_stdout(stdout)

    assert result["stdout_truncated"] is True
    excerpt_lines = result["stdout_excerpt"].count("\n") + 1
    max_lines = _limits.llm_stdout_max_lines
    assert excerpt_lines <= max_lines, (
        f"stdout excerpt should have at most {max_lines} lines, got {excerpt_lines}"
    )


def test_compact_stdout_respects_char_limit_from_settings():
    from app.agent.planner_bridge import _compact_stdout
    stdout = "data: " + "x" * (_limits.llm_stdout_char_limit + 500)

    result = _compact_stdout(stdout)

    assert result["stdout_truncated"] is True
    assert len(result["stdout_excerpt"]) <= _limits.llm_stdout_char_limit + 10, (
        "stdout excerpt should respect char limit from settings"
    )
