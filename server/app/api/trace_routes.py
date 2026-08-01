from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

from app.agent.trace_diagnostics import (
    _artifact_binding_summary,
    _context_budget_summary,
    _failure_analysis,
    _finalizer_diagnostics,
    _llm_diagnostics,
    classify_failure_mode,
    summarize_artifact_binding,
)
from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import Artifact, RunResponse

router = APIRouter(tags=["runs"])


def _store() -> MemoryStore:
    settings = get_settings()
    return MemoryStore(settings.resolved_sqlite_path)


@router.get("/runs")
def list_runs(
    project_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List persisted runs with lightweight observability metadata (paginated)."""
    runs = _store().list_runs_paginated(project_id=project_id, limit=limit, offset=offset)
    return jsonable_encoder([_run_summary(run) for run in runs])


@router.get("/runs/{run_id}")
def get_run(run_id: str, project_id: str | None = None) -> RunResponse:
    """Return the full persisted run payload for replay/debugging.

    When project_id is provided, only returns the run if it belongs to that project.
    """
    run = _store().get_run(run_id, project_id=project_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/trace")
def get_run_trace(run_id: str, project_id: str | None = None) -> dict[str, Any]:
    """Return persisted runtime events followed by derived artifact evidence."""
    store = _store()
    run = store.get_run(run_id, project_id=project_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    runtime_events = store.list_run_events(run_id)
    trace = _build_trace(run)
    events = _runtime_trace_events(runtime_events)
    offset = len(events)
    for event in trace["events"]:
        event["order"] += offset
        event["source"] = "derived"
        events.append(event)
    return jsonable_encoder({
        "run": _run_summary(run),
        "events": events,
        "event_count": len(events),
        "schema_version": 2,
        "diagnostic_summary": _diagnostic_summary(run, runtime_events),
    })


@router.get("/runs/{run_id}/trace/export")
def export_run_trace(
    run_id: str,
    project_id: str | None = None,
    level: str = Query("diagnostic"),
) -> Response:
    """Export an AI-readable diagnostic package without hidden reasoning or secrets.

    level options:
      - normal: token counts, finish_reasons, status only (no content previews)
      - diagnostic (default): head/tail previews, context budget, final payload parse
    """
    store = _store()
    run = store.get_run(run_id, project_id=project_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if level not in ("normal", "diagnostic"):
        raise HTTPException(status_code=400, detail=f"Invalid level: {level}. Supported: normal, diagnostic")

    runtime_events = store.list_run_events(run_id)
    run_dict = run.model_dump(mode="json")

    payload: dict[str, Any] = {
        "schema_version": 2,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "AI-readable Data Agent execution diagnostic. Contains observable "
            "requests, tool summaries, outputs, artifacts, and validation state; "
            "does not contain hidden chain-of-thought."
        ),
        "run": run_dict,
        "diagnostic_summary": _diagnostic_summary_v2(run, runtime_events),
        "events": runtime_events,
        "derived_trace": _build_trace(run),
        "llm_diagnostics": _llm_diag(runtime_events),
        "finalizer_diagnostics": _finalizer_diag(runtime_events),
        "context_budget_summary": _ctx_budget_summary(runtime_events),
        "artifact_binding_summary": _artifact_binding(run_dict),
        "failure_analysis": _failure_analysis(run_dict, runtime_events),
    }

    if level == "normal":
        payload = _strip_to_normal(payload)

    payload = _redact_sensitive(payload)
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="data-agent-trace-{run_id[:8]}.json"'
            )
        },
    )


@router.get("/runs/{run_id}/trace/llm")
def get_llm_tuning_log(run_id: str, project_id: str | None = None) -> dict[str, Any]:
    """Return an LLM-focused, human-readable tuning log for one run."""
    store = _store()
    run = store.get_run(run_id, project_id=project_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    payload = _build_llm_tuning_log(run, store.list_run_events(run_id))
    return jsonable_encoder(_redact_sensitive(payload))


@router.get("/runs/{run_id}/trace/llm/export")
def export_llm_tuning_log(run_id: str, project_id: str | None = None) -> Response:
    """Export the LLM-focused tuning log as JSON."""
    store = _store()
    run = store.get_run(run_id, project_id=project_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    payload = _redact_sensitive(_build_llm_tuning_log(run, store.list_run_events(run_id)))
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="data-agent-llm-tuning-{run_id[:8]}.json"'
            )
        },
    )


def _run_summary(run: RunResponse) -> dict[str, Any]:
    has_visual_report = any(_artifact_type(a) == "visual_report" for a in run.artifacts)
    return {
        "id": run.id,
        "status": run.status,
        "skill_id": run.skill_id,
        "question": run.question,
        "project_id": run.project_id,
        "artifact_count": len(run.artifacts),
        "tool_call_count": len(run.tool_calls),
        "workflow_step_count": len(run.workflow_steps),
        "has_visual_report": has_visual_report,
        "has_run_log": any(_artifact_type(a) == "run_log" for a in run.artifacts),
    }


def _build_llm_tuning_log(run: RunResponse, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a compact but detailed LLM tuning view from runtime events."""
    llm_diag = _llm_diagnostics(events)
    finalizer_diag = _finalizer_diagnostics(events)
    context_summary = _context_budget_summary(events)
    event_types: dict[str, int] = {}
    rounds: dict[int, dict[str, Any]] = {}
    ungrouped_code_events: list[dict[str, Any]] = []

    for event in events:
        event_type = event.get("type") or ""
        event_types[event_type] = event_types.get(event_type, 0) + 1
        data = event.get("data") or {}
        iteration = data.get("iteration")
        round_entry: dict[str, Any] | None = None
        if iteration is not None:
            try:
                round_entry = rounds.setdefault(int(iteration), _empty_llm_round(int(iteration)))
            except (TypeError, ValueError):
                round_entry = None

        if event_type == "llm_request_started" and round_entry is not None:
            round_entry["started_sequence"] = event.get("sequence")
            round_entry["started_elapsed_ms"] = event.get("elapsed_ms")
            round_entry["phase"] = data.get("phase") or round_entry.get("phase")
            round_entry["model"] = data.get("model") or _nested(data, "model_config", "model")
            round_entry["model_config"] = data.get("model_config") or {"model": data.get("model")}
            round_entry["request_options"] = data.get("request_options") or {
                "tool_count": len(data.get("available_tools") or []),
            }
            round_entry["finalizer_state"] = data.get("finalizer_state") or {
                "force_finalize": data.get("force_finalize"),
            }
            round_entry["context_budget"] = data.get("context_budget") or {
                "estimated_context_chars": data.get("estimated_context_chars"),
                "message_count": data.get("message_count"),
            }
            round_entry["prompt_snapshot"] = data.get("prompt_snapshot")
            round_entry["available_tools"] = data.get("available_tools") or []
            round_entry["input_metrics"] = {
                "message_count": data.get("message_count"),
                "prompt_chars": data.get("prompt_chars"),
                "message_content_chars": data.get("message_content_chars") or data.get("prompt_message_chars"),
                "tool_call_argument_chars": data.get("tool_call_argument_chars") or data.get("prompt_tool_argument_chars"),
                "tool_result_chars": data.get("tool_result_chars"),
                "estimated_context_chars": data.get("estimated_context_chars"),
                "context_budget_action": data.get("context_budget_action"),
                "execution_count": data.get("execution_count"),
                "feedback_rounds": data.get("feedback_rounds"),
            }
        elif event_type == "llm_request_completed" and round_entry is not None:
            round_entry["completed_sequence"] = event.get("sequence")
            round_entry["completed_elapsed_ms"] = event.get("elapsed_ms")
            round_entry["latency_ms"] = data.get("latency_ms") or data.get("duration_ms")
            round_entry["finish_reason"] = data.get("finish_reason")
            round_entry["usage"] = data.get("usage") or {}
            round_entry["response"] = {
                "finish_reason": data.get("finish_reason"),
                "content_chars": data.get("content_chars"),
                "content_preview": data.get("content_preview"),
                "requested_tool_names": data.get("requested_tool_names") or data.get("requested_tools") or [],
                "tool_arguments": data.get("tool_arguments") or [],
                "response_id": data.get("response_id"),
            }
        elif event_type == "llm_request_failed" and round_entry is not None:
            round_entry["status"] = "failed"
            round_entry["error"] = {
                "sequence": event.get("sequence"),
                "summary": event.get("summary"),
                "error_type": data.get("error_type"),
                "error": data.get("error"),
            }
        elif event_type == "planner_tool_requested" and round_entry is not None:
            round_entry["tool_requests"].append(_event_digest(event, extra={
                "tool": data.get("tool"),
                "arguments": data.get("arguments"),
            }))
        elif event_type in {"planner_tool_completed", "planner_tool_failed"} and round_entry is not None:
            round_entry["tool_results"].append(_event_digest(event, extra={
                "tool": data.get("tool"),
                "result": data.get("result"),
                "error_type": data.get("error_type"),
                "error": data.get("error"),
            }))
        elif event_type.startswith("code_"):
            ungrouped_code_events.append(_event_digest(event, extra={
                "step_name": data.get("step_name"),
                "returncode": data.get("returncode"),
                "table_count": data.get("table_count"),
                "chart_count": data.get("chart_count"),
                "stdout": data.get("stdout"),
                "stderr": data.get("stderr"),
            }))

    request_count = int(llm_diag.get("request_count") or event_types.get("llm_request_started", 0))
    length_count = int(llm_diag.get("length_truncation_count") or 0)
    tool_failures = event_types.get("planner_tool_failed", 0)
    notes = _llm_tuning_notes(
        request_count=request_count,
        length_truncation_count=length_count,
        tool_failure_count=tool_failures,
        context_summary=context_summary,
        finalizer_diag=finalizer_diag,
        rounds=list(rounds.values()),
    )
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "LLM tuning log for prompt/model/runtime optimization. It contains "
            "observable prompt snapshots, context budgets, tool decisions, finish "
            "reasons, token usage, latency, and finalizer recovery state."
        ),
        "run": _run_summary(run),
        "summary": {
            "request_count": request_count,
            "total_prompt_tokens": llm_diag.get("total_prompt_tokens", 0),
            "total_completion_tokens": llm_diag.get("total_completion_tokens", 0),
            "total_latency_ms": llm_diag.get("total_latency_ms", 0),
            "length_truncation_count": length_count,
            "tool_request_count": event_types.get("planner_tool_requested", 0),
            "tool_result_count": event_types.get("planner_tool_completed", 0),
            "tool_failure_count": tool_failures,
            "format_repair_attempt_count": finalizer_diag.get("format_repair_attempt_count", 0),
            "force_finalize_used": finalizer_diag.get("force_finalize_used", False),
            "detached_finalizer_used": finalizer_diag.get("detached_finalizer_used", False),
            "max_estimated_context_chars": context_summary.get("max_estimated_context_chars", 0),
            "max_message_count": context_summary.get("max_message_count", 0),
        },
        "tuning_notes": notes,
        "rounds": [rounds[key] for key in sorted(rounds)],
        "code_events": ungrouped_code_events,
        "llm_diagnostics": llm_diag,
        "finalizer_diagnostics": finalizer_diag,
        "context_budget_summary": context_summary,
    }


def _empty_llm_round(iteration: int) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": None,
        "status": "completed",
        "model": None,
        "started_sequence": None,
        "completed_sequence": None,
        "started_elapsed_ms": None,
        "completed_elapsed_ms": None,
        "latency_ms": None,
        "finish_reason": None,
        "usage": {},
        "model_config": {},
        "request_options": {},
        "finalizer_state": {},
        "context_budget": {},
        "input_metrics": {},
        "available_tools": [],
        "prompt_snapshot": None,
        "response": {},
        "tool_requests": [],
        "tool_results": [],
    }


def _event_digest(event: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "sequence": event.get("sequence"),
        "type": event.get("type"),
        "summary": event.get("summary"),
        "elapsed_ms": event.get("elapsed_ms"),
    }
    for key, value in (extra or {}).items():
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


def _nested(data: dict[str, Any], parent: str, child: str) -> Any:
    value = data.get(parent)
    return value.get(child) if isinstance(value, dict) else None


def _llm_tuning_notes(
    *,
    request_count: int,
    length_truncation_count: int,
    tool_failure_count: int,
    context_summary: dict[str, Any],
    finalizer_diag: dict[str, Any],
    rounds: list[dict[str, Any]],
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    if request_count == 0:
        notes.append({
            "severity": "warning",
            "title": "没有 LLM 调用记录",
            "detail": "该运行可能是 preflight_only、模型未配置，或来自旧版本日志；无法用于模型调优。",
        })
    if length_truncation_count > 0:
        notes.append({
            "severity": "risk",
            "title": "模型输出被 length 截断",
            "detail": "优先检查 max_tokens、finalizer prompt 长度、输出 JSON/Markdown 约束，以及是否需要更强的收口压缩。",
        })
    if tool_failure_count > 0:
        notes.append({
            "severity": "risk",
            "title": "工具调用失败",
            "detail": "重点看失败轮次的 tool_arguments、repair 事件和后续是否成功重试；这通常指向工具 schema 或提示词约束不够清晰。",
        })
    if int(context_summary.get("max_estimated_context_chars") or 0) >= 80_000:
        notes.append({
            "severity": "warning",
            "title": "上下文接近高水位",
            "detail": "关注 prompt_snapshot 中占比最大的消息，优先压缩工具结果、历史消息和数据画像摘要。",
        })
    if finalizer_diag.get("force_finalize_used"):
        notes.append({
            "severity": "info",
            "title": "触发强制收口",
            "detail": "检查强制收口前的最后几轮工具调用是否已经产生足够证据，以及 finalizer 是否拿到了最小必要证据包。",
        })
    if not any(round_item.get("prompt_snapshot") for round_item in rounds):
        notes.append({
            "severity": "info",
            "title": "缺少 prompt 快照",
            "detail": "旧运行没有记录 prompt_snapshot；新运行会保留有界 head/tail 预览，适合做提示词对比。",
        })
    return notes


def _build_trace(run: RunResponse) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    _append_event(
        events,
        event_id="run",
        event_type="run",
        name="Run",
        status=run.status,
        summary=run.question,
        data=_run_summary(run),
    )

    for index, step in enumerate(run.workflow_steps, start=1):
        _append_event(
            events,
            event_id=f"workflow-{index}-{step.id}",
            parent_id="run",
            event_type="workflow_step",
            name=step.name,
            status=step.status,
            summary=step.summary,
            data={
                "id": step.id,
                "skill_id": step.skill_id,
            },
        )

    for index, call in enumerate(run.tool_calls, start=1):
        _append_event(
            events,
            event_id=f"tool-{index}-{call.name}",
            parent_id="run",
            event_type="tool_call",
            name=call.name,
            status=call.status,
            summary=call.output_summary or call.input_summary,
            data={
                "input_summary": call.input_summary,
                "output_summary": call.output_summary,
            },
        )

    for index, artifact in enumerate(run.artifacts, start=1):
        artifact_event_id = f"artifact-{index}-{artifact.id[:8]}"
        _append_event(
            events,
            event_id=artifact_event_id,
            parent_id="run",
            event_type="artifact",
            name=artifact.title,
            status="created",
            summary=_artifact_type(artifact),
            data={
                "id": artifact.id,
                "type": _artifact_type(artifact),
                "path": str(artifact.path) if artifact.path else None,
                "created_at": artifact.created_at,
            },
        )

        if _is_visual_report_artifact(artifact) and artifact.data:
            _append_manifest_events(events, artifact_event_id, artifact.data)
        elif _artifact_type(artifact) == "run_log" and artifact.data:
            _append_run_log_events(events, artifact_event_id, artifact.data)

    events = _dedupe_trace_events(events)
    return {
        "run": _run_summary(run),
        "events": events,
        "event_count": len(events),
        "schema_version": 1,
    }


def _dedupe_trace_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    dedupe_types = {"candidate_angle", "validation_summary", "validation_gate"}
    for event in events:
        if event["type"] not in dedupe_types:
            deduped.append(event)
            continue
        fingerprint = json.dumps(
            {
                "type": event["type"],
                "name": event["name"],
                "status": event["status"],
                "summary": event.get("summary"),
                "data": event.get("data") or {},
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(event)
    for order, event in enumerate(deduped, start=1):
        event["order"] = order
    return deduped


def _runtime_trace_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"runtime-{event['sequence']}",
            "order": event["sequence"],
            "parent_id": "run",
            "type": event["type"],
            "name": _runtime_event_name(event["type"]),
            "status": _runtime_event_status(event["type"], event.get("data") or {}),
            "summary": event["summary"],
            "data": event.get("data") or {},
            "created_at": event.get("created_at"),
            "elapsed_ms": event.get("elapsed_ms"),
            "source": "runtime",
        }
        for event in events
    ]


def _diagnostic_summary_v2(
    run: RunResponse,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enhanced diagnostic summary with automatic failure classification."""
    base = _diagnostic_summary(run, events)

    # Collect evidence artifact counts from run
    run_dict = run.model_dump(mode="json") if hasattr(run, "model_dump") else {}
    artifact_summary = summarize_artifact_binding(run_dict)
    failure = classify_failure_mode(run_dict, events)

    # Collect validation failures
    validation_failed_gates: list[str] = []
    for result in run.validation_results:
        if not result.passed:
            validation_failed_gates.append(result.gate_id if hasattr(result, "gate_id") else str(result))

    # Determine likely failure mode
    length_truncation_count = failure.get("llm_length_truncation_count", 0)
    final_report_chars = failure.get("final_report_chars")  # can be None
    empty_or_tiny = failure.get("empty_or_tiny_report")
    evidence_artifacts = artifact_summary.get("table_artifacts", 0) + artifact_summary.get("chart_artifacts", 0)

    likely_failure_mode = failure.get("likely_failure_mode")
    if not likely_failure_mode and empty_or_tiny is True:
        if length_truncation_count >= 2:
            likely_failure_mode = "repeated_finalizer_length_truncation"
        elif evidence_artifacts > 0:
            likely_failure_mode = "evidence_generated_but_empty_report"
        elif validation_failed_gates:
            likely_failure_mode = "report_artifact_binding_failed"

    recommended_debug_focus: list[str] = []
    if likely_failure_mode == "repeated_finalizer_length_truncation":
        recommended_debug_focus = [
            "planner finalizer",
            "context compaction",
            "final payload quality gate",
        ]
    elif likely_failure_mode == "evidence_generated_but_empty_report":
        recommended_debug_focus = [
            "finalizer prompt construction",
            "evidence bundling for finalizer",
            "JSON parsing in _coerce_final_payload",
        ]
    elif likely_failure_mode == "report_artifact_binding_failed":
        recommended_debug_focus = [
            "artifact assembly",
            "web report rendering",
            "evidence-to-report binding",
        ]

    return {
        **base,
        "likely_failure_stage": failure.get("likely_failure_stage"),
        "likely_failure_mode": likely_failure_mode,
        "evidence_generation_completed": failure.get("evidence_generation_completed", False),
        "table_artifact_count": artifact_summary.get("table_artifacts", 0),
        "chart_artifact_count": artifact_summary.get("chart_artifacts", 0),
        "final_report_chars": final_report_chars,
        "llm_length_truncation_count": length_truncation_count,
        "detached_finalizer_used": failure.get("detached_finalizer_used", False),
        "force_finalize_used": failure.get("force_finalize_used", False),
        "empty_or_tiny_report": empty_or_tiny,
        "validation_failed_gates": validation_failed_gates,
        "recommended_debug_focus": recommended_debug_focus,
    }


def _llm_diag(events: list[dict[str, Any]]) -> dict[str, Any]:
    return _llm_diagnostics(events)


def _finalizer_diag(events: list[dict[str, Any]]) -> dict[str, Any]:
    return _finalizer_diagnostics(events)


def _ctx_budget_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    return _context_budget_summary(events)


def _artifact_binding(run_dict: dict[str, Any] | None) -> dict[str, Any]:
    return _artifact_binding_summary(run_dict)


def _strip_to_normal(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip content previews and full diagnostic detail for 'normal' level export."""
    for event in payload.get("events", []):
        data = event.get("data") or {}
        if "content_preview" in data:
            # Keep only chars count and truncated flag, remove head/tail
            preview = data.pop("content_preview")
            data["content_preview"] = {
                "chars": preview.get("chars", 0),
                "truncated": preview.get("truncated", False),
            }
        for key in ("tool_arguments", "tool_result_chars"):
            data.pop(key, None)
    return payload


def _diagnostic_summary(
    run: RunResponse,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_events = [
        event
        for event in events
        if _runtime_event_status(event["type"], event.get("data") or {}) == "failed"
    ]
    derived_failures = [
        {
            "sequence": None,
            "type": "workflow_step",
            "summary": step.summary or step.name,
        }
        for step in run.workflow_steps
        if step.status in {"failed", "failure"}
    ]
    derived_failures.extend(
        {
            "sequence": None,
            "type": "tool_call",
            "summary": call.output_summary or call.input_summary or call.name,
        }
        for call in run.tool_calls
        if call.status in {"failed", "failure"}
    )
    derived_failures.extend(
        {
            "sequence": None,
            "type": "validation_gate",
            "summary": result.message,
        }
        for result in run.validation_results
        if not result.passed
    )
    event_types: dict[str, int] = {}
    for event in events:
        event_types[event["type"]] = event_types.get(event["type"], 0) + 1
    validation_failures = sum(
        1 for result in run.validation_results if not result.passed
    )
    llm_calls = event_types.get("llm_request_started", 0)
    failure_details = [
        {
            "sequence": event["sequence"],
            "type": event["type"],
            "summary": event["summary"],
        }
        for event in failed_events
    ] or derived_failures
    return {
        "status": run.status,
        "event_count": len(events),
        "event_types": event_types,
        "llm_call_count": llm_calls,
        "analysis_execution_count": event_types.get("code_execution_started", 0),
        "failed_event_count": len(failure_details),
        "failed_events": failure_details,
        "tool_call_count": len(run.tool_calls),
        "artifact_count": len(run.artifacts),
        "validation_failure_count": validation_failures,
        "validation_passed": run.validation_passed,
    }


def _runtime_event_name(event_type: str) -> str:
    names = {
        "run_started": "任务启动",
        "context_loaded": "上下文加载",
        "dataset_profile_started": "数据画像开始",
        "dataset_profile_completed": "数据画像完成",
        "preflight_completed": "运行前检查",
        "planning_started": "模型规划开始",
        "planning_failed": "模型规划失败",
        "llm_request_started": "LLM 请求",
        "llm_request_completed": "LLM 响应",
        "llm_request_failed": "LLM 请求失败",
        "planner_tool_requested": "规划器工具请求",
        "planner_tool_completed": "规划器工具完成",
        "feedback_evaluated": "质量反馈",
        "planner_finalization_forced": "强制报告收口",
        "planner_finalized": "报告收口完成",
        "planner_finalizer_length_truncated": "长度截断",
        "planner_final_payload_parsed": "最终 Payload 解析",
        "planner_detached_finalizer_started": "分离式收口启动",
        "planner_final_output_rejected": "输出格式拒绝",
        "planner_final_output_format_repair_started": "格式修复启动",
        "planner_final_output_format_repair_completed": "格式修复完成",
        "planner_final_output_format_repair_failed": "格式修复失败",
        "planner_tool_failed": "工具调用失败",
        "code_generated": "分析代码生成",
        "code_execution_started": "分析代码执行",
        "code_execution_completed": "分析代码结果",
        "diagnosis_completed": "诊断完成",
        "report_generation_started": "报告生成开始",
        "report_generated": "报告生成完成",
        "validation_started": "验证开始",
        "validation_completed": "验证完成",
    }
    return names.get(event_type, event_type)


def _runtime_event_status(event_type: str, data: dict[str, Any]) -> str:
    if event_type.endswith("_failed") or event_type in {"planning_failed"}:
        return "failed"
    if event_type == "code_execution_completed":
        return "completed" if data.get("returncode") == 0 else "failed"
    if event_type == "validation_completed":
        return "passed" if data.get("validation_passed") else "failed"
    if event_type.endswith("_started") or event_type == "planner_tool_requested":
        return "running"
    return "completed"


def _redact_sensitive(value: Any) -> Any:
    sensitive_names = {
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
    }
    if isinstance(value, dict):
        return {
            key: _redact_sensitive(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key), sensitive_names)
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _is_sensitive_key(key: str, sensitive_names: set[str]) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in sensitive_names:
        return True
    return normalized.endswith(("_api_key", "_password", "_secret", "_credential"))


def _append_manifest_events(
    events: list[dict[str, Any]],
    parent_id: str,
    data: dict[str, Any],
) -> None:
    manifest = data.get("manifest") if isinstance(data, dict) else None
    snapshot = data.get("snapshot") if isinstance(data, dict) else None
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    for index, source in enumerate(_as_list(manifest.get("sources")), start=1):
        if not isinstance(source, dict):
            continue
        label = source.get("label") or source.get("id") or f"Source {index}"
        query = source.get("query") if isinstance(source.get("query"), dict) else {}
        summary = query.get("description") or query.get("sql") or source.get("path")
        _append_event(
            events,
            event_id=f"source-{index}-{source.get('id', index)}",
            parent_id=parent_id,
            event_type="source",
            name=str(label),
            status="recorded",
            summary=str(summary) if summary is not None else None,
            data=source,
        )

    for index, evidence in enumerate(_as_list(snapshot.get("evidence_map")), start=1):
        if not isinstance(evidence, dict):
            continue
        title = evidence.get("title") or evidence.get("id") or f"Evidence {index}"
        _append_event(
            events,
            event_id=f"evidence-{index}-{evidence.get('id', index)}",
            parent_id=parent_id,
            event_type="evidence",
            name=str(title),
            status="recorded",
            summary=_evidence_summary(evidence),
            data=evidence,
        )

    for index, angle in enumerate(_as_list(manifest.get("candidate_angles")), start=1):
        if not isinstance(angle, dict):
            continue
        question = angle.get("question") or f"Candidate angle {index}"
        _append_event(
            events,
            event_id=f"candidate-angle-{index}-{angle.get('id', index)}",
            parent_id=parent_id,
            event_type="candidate_angle",
            name=str(question),
            status="selected" if angle.get("selected") else "considered",
            summary=_angle_summary(angle),
            data=angle,
        )

    _append_validation_events(events, parent_id, data)


def _append_run_log_events(
    events: list[dict[str, Any]],
    parent_id: str,
    data: dict[str, Any],
) -> None:
    candidate_angles = _as_list(data.get("candidate_angles"))
    for index, angle in enumerate(candidate_angles, start=1):
        if not isinstance(angle, dict):
            continue
        question = angle.get("question") or f"Candidate angle {index}"
        _append_event(
            events,
            event_id=f"run-log-candidate-angle-{index}-{angle.get('id', index)}",
            parent_id=parent_id,
            event_type="candidate_angle",
            name=str(question),
            status="selected" if angle.get("selected") else "considered",
            summary=_angle_summary(angle),
            data=angle,
        )

    _append_validation_events(events, parent_id, data)


def _append_validation_events(
    events: list[dict[str, Any]],
    parent_id: str,
    data: dict[str, Any],
) -> None:
    validation_results = _as_list(data.get("validation_results"))
    if not validation_results:
        return

    passed = data.get("validation_passed")
    _append_event(
        events,
        event_id=f"{parent_id}-validation-summary",
        parent_id=parent_id,
        event_type="validation_summary",
        name="Validation summary",
        status="completed" if passed else "failed",
        summary=f"{sum(1 for item in validation_results if _truthy(item, 'passed'))}/{len(validation_results)} gates passed",
        data={"validation_passed": passed, "gate_count": len(validation_results)},
    )

    for index, gate in enumerate(validation_results, start=1):
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("gate_id") or gate.get("id") or f"gate_{index}"
        _append_event(
            events,
            event_id=f"{parent_id}-validation-{index}-{gate_id}",
            parent_id=parent_id,
            event_type="validation_gate",
            name=str(gate_id),
            status="passed" if gate.get("passed") else "failed",
            summary=gate.get("message"),
            data=gate,
        )


def _append_event(
    events: list[dict[str, Any]],
    *,
    event_id: str,
    event_type: str,
    name: str,
    status: str,
    parent_id: str | None = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    event = {
        "id": event_id,
        "order": len(events) + 1,
        "parent_id": parent_id,
        "type": event_type,
        "name": name,
        "status": status,
        "summary": summary,
        "data": data or {},
    }
    events.append(event)


def _artifact_type(artifact: Artifact) -> str:
    return artifact.type.value if hasattr(artifact.type, "value") else str(artifact.type)


def _is_visual_report_artifact(artifact: Artifact) -> bool:
    return _artifact_type(artifact) == "visual_report"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _truthy(item: Any, key: str) -> bool:
    return bool(item.get(key)) if isinstance(item, dict) else False


def _evidence_summary(evidence: dict[str, Any]) -> str:
    pieces = []
    if evidence.get("type"):
        pieces.append(str(evidence["type"]))
    if evidence.get("source_dataset"):
        pieces.append(f"source={evidence['source_dataset']}")
    if evidence.get("step_id"):
        pieces.append(f"step={evidence['step_id']}")
    if evidence.get("row_count") is not None:
        pieces.append(f"rows={evidence['row_count']}")
    return ", ".join(pieces)


def _angle_summary(angle: dict[str, Any]) -> str:
    scores = []
    for key in ("impact_score", "confidence_score", "data_sufficiency_score"):
        if angle.get(key) is not None:
            scores.append(f"{key}={angle[key]}")
    if angle.get("expected_evidence"):
        scores.append(str(angle["expected_evidence"]))
    return "; ".join(scores)
