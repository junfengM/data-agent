"""Factory for the execute_step closure used by the LLM planner."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.models.schemas import Artifact, ArtifactType, RunEventType, RunResponse, ToolCall
from app.tools.chart_contract import FILE_CHART_TYPES
from app.tools.execution import run_analysis_code
from app.tools.redaction import redact_local_paths, safe_file_artifact_ref

# ---------------------------------------------------------------------------
# LLM context compaction limits (sourced from settings)
# ---------------------------------------------------------------------------


def _limits():
    return get_settings()


def create_execute_step(
    run_dir: Path,
    dataset_paths: list[Path],
    generated_code_execution: str,
    run: RunResponse,
    emit: Any,
    step_results_list: list[dict],
):
    """Create an execute_step closure that captures run state.

    Returns an async function that executes LLM-generated analysis code,
    records artifacts, and appends step results.
    """

    async def execute_step(code: str, step_name: str, step_desc: str) -> dict:
        await emit(
            RunEventType.CODE_GENERATED,
            f"\u5df2\u751f\u6210\u5206\u6790\u4ee3\u7801\uff1a{step_name}\u3002",
            step_name=step_name,
            step_description=step_desc,
            code=code,
        )
        await emit(
            RunEventType.CODE_EXECUTION_STARTED,
            f"\u5f00\u59cb\u6267\u884c\u5206\u6790\u4ee3\u7801\uff1a{step_name}\u3002",
            step_name=step_name,
        )
        result = run_analysis_code(
            code=code,
            run_dir=run_dir,
            dataset_paths=dataset_paths,
            generated_code_execution=generated_code_execution,
        )
        await emit(
            RunEventType.CODE_EXECUTION_COMPLETED,
            f"\u4ee3\u7801\u6267\u884c\u5b8c\u6210\uff1a\u8fd4\u56de\u7801 {result.returncode}\uff0c\u751f\u6210 {len(result.tables)} \u4e2a\u8868\u683c\u3001{len(result.charts)} \u4e2a\u56fe\u8868\u3002",
            step_name=step_name,
            returncode=result.returncode,
            stdout=result.stdout[:3000] if result.stdout else "",
            stderr=redact_local_paths(result.stderr[:1000]) if result.stderr else "",
            table_count=len(result.tables),
            chart_count=len(result.charts),
        )

        run.tool_calls.append(
            ToolCall(
                name="analysis_step",
                input_summary=f"{step_name}: {step_desc[:80]}" if step_desc else step_name,
                output_summary=(
                    f"Returned {result.returncode}, "
                    f"{len(result.tables)} table(s), "
                    f"{len(result.charts)} chart(s)"
                ),
                status="completed" if result.returncode == 0 else "failed",
            )
        )

        for table_info in result.tables:
            run.artifacts.append(
                Artifact(
                    type=ArtifactType.table,
                    title=table_info["name"],
                    content=f"Table: {table_info['name']} ({table_info.get('rows', '?')} rows)",
                    data={
                        "columns": [{"key": col, "label": col} for col in table_info.get("columns", [])],
                        "rows": table_info.get("preview", []),
                        "source": safe_file_artifact_ref(table_info.get("path", "")),
                    },
                )
            )

        for chart_info in result.charts:
            is_file = chart_info.get("type") in FILE_CHART_TYPES
            chart_path = safe_file_artifact_ref(chart_info.get("path", ""))
            chart_asset_name = Path(chart_path).name if chart_path else ""
            run.artifacts.append(
                Artifact(
                    type=ArtifactType.chart,
                    title=chart_info["name"],
                    content=f"Chart: {chart_info['name']}",
                    data={
                        "chart_type": chart_info.get("type", "unknown"),
                        "render_mode": "file" if is_file else "vega",
                        "path": chart_path,
                        "asset_name": chart_asset_name,
                    },
                )
            )

        full_step_payload = {
            "name": step_name,
            "description": step_desc,
            "code": code,
            "returncode": result.returncode,
            "status": "completed" if result.returncode == 0 else "failed",
            "stdout": result.stdout[:_limits().llm_stdout_char_limit] if result.stdout else "",
            "stderr": redact_local_paths(result.stderr[:_limits().llm_stderr_char_limit]) if result.stderr else "",
            "tables": _sanitize_step_tables(result.tables),
            "charts": _sanitize_step_charts(result.charts),
        }
        step_results_list.append(full_step_payload)
        return _compact_step_payload_for_llm(full_step_payload)

    return execute_step


def _sanitize_step_tables(tables: list[dict]) -> list[dict]:
    return [
        {**t, "path": safe_file_artifact_ref(t.get("path", ""))}
        for t in tables
    ]


def _sanitize_step_charts(charts: list[dict]) -> list[dict]:
    return [
        {**c, "path": safe_file_artifact_ref(c.get("path", ""))}
        for c in charts
    ]


# ---------------------------------------------------------------------------
# LLM context compaction helpers
# ---------------------------------------------------------------------------


def _compact_stdout(stdout: str, *, limit: int | None = None) -> dict:
    text = stdout or ""
    if not text:
        return {"stdout_excerpt": "", "stdout_truncated": False}

    if limit is None:
        limit = _limits().llm_stdout_char_limit

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]

    important_lines = [
        line
        for line in lines
        if any(ch.isdigit() for ch in line) or "%" in line or ":" in line or "=" in line
    ]

    max_lines = _limits().llm_stdout_max_lines
    selected = important_lines[:max_lines] if important_lines else lines[:max_lines]
    excerpt = "\n".join(selected)

    truncated = len(excerpt) > limit or len(text) > len(excerpt)
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rstrip() + "\n..."

    return {
        "stdout_excerpt": excerpt,
        "stdout_truncated": truncated,
    }


def _compact_step_table_for_llm(table: dict) -> dict:
    columns = list(table.get("columns") or [])
    preview = list(table.get("preview") or [])
    rows = table.get("rows")
    path = safe_file_artifact_ref(table.get("path", ""))
    is_wide = len(columns) > _limits().llm_wide_table_column_threshold

    base = {
        "name": table.get("name"),
        "rows": rows,
        "columns_count": len(columns),
        "path": path,
    }

    if is_wide:
        col_sample = columns[:_limits().llm_wide_table_column_sample]
        base.update({
            "columns": col_sample,
            "columns_sample": col_sample,
            "preview": [],
            "preview_omitted": True,
            "omission_reason": (
                f"wide table with {len(columns)} columns; use artifact path for details"
            ),
        })
        return base

    kept_columns = columns[:_limits().llm_table_preview_columns]
    compact_preview = []
    for row in preview[:_limits().llm_table_preview_rows]:
        if isinstance(row, dict):
            compact_preview.append({col: row.get(col) for col in kept_columns})

    base.update({
        "columns": kept_columns,
        "preview": compact_preview,
        "preview_rows": len(compact_preview),
        "preview_columns": len(kept_columns),
        "preview_omitted": False,
    })
    return base


def _compact_step_tables_for_llm(tables: list[dict]) -> list[dict]:
    return [_compact_step_table_for_llm(table) for table in tables]


def _compact_step_charts_for_llm(charts: list[dict]) -> list[dict]:
    compact = []
    for chart in charts:
        path_val = safe_file_artifact_ref(chart.get("path", ""))
        compact.append({
            "name": chart.get("name"),
            "type": chart.get("type", "unknown"),
            "path": path_val,
        })
    return compact


def _compact_step_payload_for_llm(payload: dict) -> dict:
    returncode = payload.get("returncode")
    failed = payload.get("status") == "failed" or returncode not in (0, None)

    stdout_info = _compact_stdout(payload.get("stdout") or "")
    stdout_excerpt = stdout_info["stdout_excerpt"]

    compact = {
        "name": payload.get("name"),
        "description": payload.get("description"),
        "returncode": returncode,
        "status": payload.get("status"),
        "code_ref": payload.get("name"),
        "code_chars": len(payload.get("code") or ""),
        "stdout": stdout_excerpt,
        **stdout_info,
        "stderr": (
            str(payload.get("stderr") or "")[:_limits().llm_stderr_char_limit]
            if failed
            else ""
        ),
        "tables": _compact_step_tables_for_llm(payload.get("tables") or []),
        "charts": _compact_step_charts_for_llm(payload.get("charts") or []),
    }

    if failed:
        code = payload.get("code") or ""
        compact["code_excerpt"] = code[:_limits().llm_failed_code_excerpt_limit]
        compact["code_excerpt_truncated"] = len(code) > _limits().llm_failed_code_excerpt_limit
        for table in compact["tables"]:
            table["partial"] = True
        for chart in compact["charts"]:
            chart["partial"] = True

    return compact
