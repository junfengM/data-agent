"""Run lifecycle helpers: event emission, workflow templates, step completion, run log markdown."""
from __future__ import annotations

import time
from typing import Any

from app.models.schemas import RunResponse, WorkflowStep


def create_event_emitter(
    store: Any,
    run: RunResponse,
    run_started_at: float,
    event_sink: Any,
):
    """Create an emit closure that records run events and streams to event sink."""

    async def emit(event_type: str, summary: str, **data: Any) -> None:
        elapsed_ms = int((time.perf_counter() - run_started_at) * 1000)
        sequence = store.record_run_event(
            run.id,
            event_type=event_type,
            summary=summary,
            data=data,
            elapsed_ms=elapsed_ms,
        )
        store.record_run(run)
        if event_sink is not None:
            await event_sink({
                "sequence": sequence,
                "type": event_type,
                "summary": summary,
                "data": data,
                "elapsed_ms": elapsed_ms,
            })

    return emit


def build_workflow_template(skill_id: str) -> list[WorkflowStep]:
    return [
        WorkflowStep(id="analysis", name="Analyze data", skill_id=skill_id, status="pending", summary=""),
        WorkflowStep(id="diagnosis", name="Generate diagnosis", skill_id=skill_id, status="pending", summary=""),
        WorkflowStep(id="report", name="Create report", skill_id=skill_id, status="pending", summary=""),
    ]


def complete_step(run: RunResponse, step_id: str, summary: str) -> None:
    for step in run.workflow_steps:
        if step.id == step_id:
            step.status = "completed"
            step.summary = summary
            return


def build_run_log_markdown(run: RunResponse, data: dict[str, Any]) -> str:
    lines = [
        "# \u5de5\u4f5c\u6d41\u65e5\u5fd7",
        "",
        f"- Run ID: {run.id}",
        f"- Status: {run.status}",
        f"- Skill: {run.skill_id}",
        f"- Artifacts: {len(run.artifacts)}",
        f"- Validation passed: {data.get('validation_passed')}",
        "",
        "## Selected skills",
        ", ".join(data.get("selected_skills") or []) or "none",
        "",
        "## Caveats",
        "\n".join(f"- {item}" for item in (data.get("caveats") or [])) or "none",
        "",
        "## Next checks",
        "\n".join(f"- {item}" for item in (data.get("next_checks") or [])) or "none",
    ]

    failed_tool_calls = [
        tc for tc in (data.get("tool_calls") or [])
        if tc.get("status") in {"failed", "error"}
    ]
    if failed_tool_calls:
        lines.extend(["", "## Failed tool calls"])
        for tc in failed_tool_calls:
            lines.extend([
                "",
                f"### {tc.get('name', '?')}",
                f"- Status: {tc.get('status', '?')}",
                f"- Input: {tc.get('input_summary', '')}",
            ])
            output_summary = tc.get("output_summary")
            if output_summary:
                lines.append(f"- Output:\n```\n{output_summary}\n```")

    step_results = data.get("step_results") or []
    if step_results:
        lines.extend(["", "## Analysis step results"])
    for sr in step_results:
        lines.append("")
        lines.append(f"### Step: {sr.get('name', '?')}")
        lines.append(f"- Status: {sr.get('status', '?')}")
        if sr.get("status") == "failed":
            stderr = sr.get("stderr", "")
            stdout = sr.get("stdout", "")
            if stderr:
                lines.append(f"- stderr:\n```\n{stderr}\n```")
            if stdout:
                lines.append(f"- stdout:\n```\n{stdout[:2000]}\n```")
    return "\n".join(lines)
