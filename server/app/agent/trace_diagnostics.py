"""Diagnostic helpers for trace analysis and export.

These functions provide compact, human- and AI-readable summaries of
planner executions without leaking full LLM content or secrets.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def safe_preview(
    text: str | None,
    head: int = 1200,
    tail: int = 1200,
) -> dict[str, Any]:
    """Return a compact preview of text content without full exposure."""
    if not text:
        return {"chars": 0, "head": "", "tail": "", "truncated": False}
    chars = len(text)
    truncated = chars > (head + tail)
    return {
        "chars": chars,
        "head": text[:head],
        "tail": text[-tail:] if truncated else "",
        "truncated": truncated,
    }


def safe_hash_text(text: str | None) -> str:
    """Return a short, stable hash of text content for diff/comparison."""
    if not text:
        return "empty"
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


BAD_MARKER_PATTERNS: list[str] = [
    r"<\w+parameter\b",
    r"</\w+parameter\b",
    r"[<]zml",
    r"</?[^>]*(?:parameter|tool_calls|invoke)",
    r"df\['",
    r"pd\.to_datetime",
    r"groupby\(",
    r"print\(",
    r"import pandas",
    r"dataset_paths\[",
    r"repair_of",
]
_BAD_MARKER_RE = re.compile("|".join(BAD_MARKER_PATTERNS), re.IGNORECASE)


def check_report_sanity(
    report_md: str | None,
    chart_specs: list | None = None,
    chart_ref_count: int = 0,
    evidence_ref_count: int = 0,
    has_evidence: bool = False,
) -> dict[str, Any]:
    """Check report_md for code/DSML contamination and evidence integration.

    Returns a dict with sanity verdict and diagnostic details.
    """
    md = report_md or ""
    bad_markers_found: list[str] = []
    for pattern in BAD_MARKER_PATTERNS:
        if re.search(pattern, md, re.IGNORECASE):
            bad_markers_found.append(pattern)

    code_marker_count = len(bad_markers_found)
    report_sanity_passed = True
    failure_reason: str | None = None

    # Multiple code/DSML markers → contaminated
    if code_marker_count >= 2:
        report_sanity_passed = False
        failure_reason = "report_content_contaminated_by_tool_call_or_code"
    elif code_marker_count >= 1 and len(md) < 500:
        # Single marker + tiny report → likely contamination
        report_sanity_passed = False
        failure_reason = "report_content_contaminated_by_tool_call_or_code"

    # Evidence not integrated: has evidence but report has no chart refs/chart specs/evidence refs
    chart_specs = chart_specs or []
    if has_evidence and len(chart_specs) == 0 and chart_ref_count == 0 and evidence_ref_count == 0:
        if not report_sanity_passed:
            pass  # already failed
        else:
            report_sanity_passed = False
            failure_reason = "evidence_not_integrated"

    return {
        "report_sanity_passed": report_sanity_passed,
        "failure_reason": failure_reason,
        "report_md_bad_markers": bad_markers_found,
        "report_md_code_marker_count": code_marker_count,
    }


def count_report_features(report_md: str | None) -> dict[str, Any]:
    """Count structural features in a Markdown report."""
    md = report_md or ""
    heading_count = len(re.findall(r"^#{1,6}\s", md, flags=re.MULTILINE))
    # Count markdown table rows (pipe syntax)
    table_row_count = len(re.findall(r"^\|.*\|\s*$", md, flags=re.MULTILINE))
    # Count chart references (.html links)
    chart_ref_count = len(re.findall(r"\.(html|png|svg)", md, flags=re.IGNORECASE))
    # Count evidence-like references
    evidence_ref_count = len(re.findall(r"evidence|证据|来源", md, flags=re.IGNORECASE))
    # Count JSON chart_specs references inside text (not exact parse, for quick check)
    chart_specs_count = 0  # caller should pass from parsed payload
    # Count candidate angle mentions
    candidate_angles_count = len(re.findall(r"candidate_angle|分析角度|impact_score", md, flags=re.IGNORECASE))

    return {
        "report_md_chars": len(md),
        "heading_count": heading_count,
        "table_row_count": table_row_count,
        "chart_ref_count": chart_ref_count,
        "evidence_ref_count": evidence_ref_count,
        "chart_specs_text_ref_count": chart_specs_count,
        "candidate_angles_text_ref_count": candidate_angles_count,
        "empty_or_tiny": len(md) < 500,
    }


def summarize_context_budget(
    messages: list[dict[str, Any]] | None,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize context budget from messages and tool results."""
    msgs = messages or []
    results = tool_results or []

    system_chars = 0
    user_chars = 0
    assistant_chars = 0
    tool_result_chars = 0
    tool_call_argument_chars = 0
    largest_items: list[dict[str, Any]] = []

    for index, msg in enumerate(msgs):
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        content_chars = len(content)

        if role == "system":
            system_chars += content_chars
        elif role == "user":
            user_chars += content_chars
        elif role == "assistant":
            assistant_chars += content_chars
        elif role == "tool":
            tool_result_chars += content_chars

        tc_arg_chars = 0
        for tc in msg.get("tool_calls") or []:
            func = tc.get("function") or {}
            args = str(func.get("arguments") or "")
            tc_arg_chars += len(args)
        tool_call_argument_chars += tc_arg_chars

        largest_items.append({
            "index": index,
            "role": role,
            "content_chars": content_chars,
            "tool_call_argument_chars": tc_arg_chars,
            "total_chars": content_chars + tc_arg_chars,
        })

    largest_items = sorted(
        largest_items, key=lambda x: x["total_chars"], reverse=True
    )[:8]

    estimated_context_chars = (
        system_chars + user_chars + assistant_chars
        + tool_result_chars + tool_call_argument_chars
    )

    return {
        "estimated_context_chars": estimated_context_chars,
        "message_count": len(msgs),
        "system_chars": system_chars,
        "user_chars": user_chars,
        "assistant_chars": assistant_chars,
        "tool_result_chars": tool_result_chars,
        "tool_call_argument_chars": tool_call_argument_chars,
        "largest_items": largest_items,
    }


def classify_failure_mode(
    run: dict[str, Any] | None,
    events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Classify the likely failure mode from run data and runtime events."""
    run_data = run or {}
    evts = events or []

    # Count length truncations
    llm_length_truncation_count = sum(
        1 for e in evts
        if e.get("type") in ("llm_request_completed",)
        and (e.get("data") or {}).get("finish_reason") == "length"
    )

    # Count evidence artifacts from run
    artifacts = run_data.get("artifacts") or []
    table_count = sum(
        1 for a in artifacts
        if str(a.get("type") or "").endswith("table")
    )
    chart_count = sum(
        1 for a in artifacts
        if str(a.get("type") or "").endswith("chart")
    )

    # Get final report chars from payload parsed event
    final_report_chars: int | None = None
    empty_or_tiny_report: bool | None = None
    found_payload_event = False
    for e in evts:
        if e.get("type") == "planner_final_payload_parsed":
            data = e.get("data") or {}
            final_report_chars = data.get("report_md_chars", 0)
            empty_or_tiny_report = final_report_chars < 500
            found_payload_event = True
            break

    # Fallback: infer from markdown_report artifact content if no payload event
    if not found_payload_event:
        for a in artifacts:
            a_type = str(a.get("type") or "")
            if a_type in ("markdown_report", "structured_report"):
                content = a.get("content") or ""
                final_report_chars = len(content)
                empty_or_tiny_report = final_report_chars < 500
                break

    # Also check validation results from run
    validation_results = run_data.get("validation_results") or []
    validation_failed_gates: list[str] = [
        str(r.get("gate_id") or r.get("id") or "")
        for r in validation_results
        if not r.get("passed", True)
    ]

    # Build failure analysis
    likely_failure_stage: str | None = None
    likely_failure_mode: str | None = None

    # Extract final payload parse event for sanity data
    final_payload_data: dict[str, Any] | None = None
    for e in evts:
        if e.get("type") == "planner_final_payload_parsed":
            final_payload_data = e.get("data") or {}
            break

    # Run sanity check if we have report content
    report_sanity_passed: bool | None = None
    report_md_bad_markers: list[str] = []
    report_md_code_marker_count = 0
    if final_payload_data:
        # Use the already-parsed quality_flags to check for contamination
        bad_markers_from_event = final_payload_data.get("report_md_bad_markers", [])
        code_marker_from_event = final_payload_data.get("report_md_code_marker_count", 0)
        if bad_markers_from_event:
            report_md_bad_markers = bad_markers_from_event
            report_md_code_marker_count = code_marker_from_event
            report_sanity_passed = False
        elif "report_content_contaminated" in str(final_payload_data.get("quality_flags", [])):
            report_sanity_passed = False
        else:
            report_sanity_passed = True

    # Classify failure mode with priority: contamination > evidence gap > length > empty
    if report_sanity_passed is False and report_md_code_marker_count >= 2:
        likely_failure_stage = "final_report_synthesis"
        likely_failure_mode = "report_content_contaminated_by_tool_call_or_code"
    elif report_sanity_passed is False and (table_count > 0 or chart_count > 0) and (
        final_payload_data is not None
        and final_payload_data.get("chart_specs_count", 0) == 0
        and final_payload_data.get("chart_ref_count", 0) == 0
        and final_payload_data.get("evidence_ref_count", 0) == 0
    ):
        likely_failure_stage = "final_report_synthesis"
        likely_failure_mode = "evidence_not_integrated"
    elif empty_or_tiny_report is True:
        if llm_length_truncation_count >= 2:
            likely_failure_stage = "final_report_synthesis"
            likely_failure_mode = "repeated_finalizer_length_truncation"
        elif table_count > 0 or chart_count > 0:
            likely_failure_stage = "final_report_synthesis"
            likely_failure_mode = "evidence_generated_but_empty_report"
        elif validation_failed_gates:
            likely_failure_stage = "final_report_synthesis"
            likely_failure_mode = "report_artifact_binding_failed"
        else:
            likely_failure_stage = "final_report_synthesis"
            likely_failure_mode = "empty_report_unknown_cause"

    evidence_generation_completed = table_count > 0 or chart_count > 0
    detached_finalizer_used = False
    force_finalize_used = False
    for e in evts:
        if e.get("type") == "planner_detached_finalizer_started":
            detached_finalizer_used = True
        if e.get("type") == "planner_finalization_forced":
            force_finalize_used = True
        if e.get("type") == "llm_request_started" and (e.get("data") or {}).get("force_finalize"):
            force_finalize_used = True

    recommended_debug_focus: list[str] = []
    if likely_failure_mode == "report_content_contaminated_by_tool_call_or_code":
        recommended_debug_focus = [
            "report content sanity gate",
            "model output parsing",
            "format repair integrity",
        ]
    elif likely_failure_mode == "evidence_not_integrated":
        recommended_debug_focus = [
            "evidence-to-report binding",
            "chart_specs generation",
            "finalizer prompt evidence instructions",
        ]
    elif likely_failure_mode == "repeated_finalizer_length_truncation":
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

    return {
        "likely_failure_stage": likely_failure_stage,
        "likely_failure_mode": likely_failure_mode,
        "evidence_generation_completed": evidence_generation_completed,
        "table_artifact_count": table_count,
        "chart_artifact_count": chart_count,
        "final_report_chars": final_report_chars,
        "llm_length_truncation_count": llm_length_truncation_count,
        "detached_finalizer_used": detached_finalizer_used,
        "force_finalize_used": force_finalize_used,
        "empty_or_tiny_report": empty_or_tiny_report,
        "validation_failed_gates": validation_failed_gates,
        "recommended_debug_focus": recommended_debug_focus,
        "report_sanity_passed": report_sanity_passed,
        "report_md_bad_markers": report_md_bad_markers,
        "report_md_code_marker_count": report_md_code_marker_count,
    }


def summarize_artifact_binding(run: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize artifact binding state from a run."""
    run_data = run or {}
    artifacts = run_data.get("artifacts") or []

    by_type: dict[str, int] = {}
    for a in artifacts:
        t = str(a.get("type") or "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    table_artifacts = sum(
        1 for a in artifacts
        if str(a.get("type") or "").endswith("table")
    )
    chart_artifacts = sum(
        1 for a in artifacts
        if str(a.get("type") or "").endswith("chart")
    )
    visual_report_count = sum(
        1 for a in artifacts
        if str(a.get("type") or "") == "visual_report"
    )
    run_log_count = sum(
        1 for a in artifacts
        if str(a.get("type") or "") == "run_log"
    )

    return {
        "total_artifacts": len(artifacts),
        "by_type": by_type,
        "table_artifacts": table_artifacts,
        "chart_artifacts": chart_artifacts,
        "visual_report_count": visual_report_count,
        "run_log_count": run_log_count,
        "has_evidence": table_artifacts > 0 or chart_artifacts > 0,
    }


def _llm_diagnostics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract LLM-level diagnostics from runtime events, merging started/completed."""
    starts: dict[int, dict[str, Any]] = {}
    completions: dict[int, dict[str, Any]] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_latency_ms = 0
    length_truncation_count = 0

    for e in events:
        t = e.get("type") or ""
        data = e.get("data") or {}
        if t == "llm_request_started":
            iteration = data.get("iteration")
            if iteration is not None:
                starts[int(iteration)] = {
                    "iteration": int(iteration),
                    "phase": data.get("phase"),
                    "model": data.get("model"),
                    "force_finalize": data.get("force_finalize"),
                    "estimated_context_chars": data.get("estimated_context_chars"),
                    "message_count": data.get("message_count"),
                }
        elif t == "llm_request_completed":
            iteration = data.get("iteration")
            if iteration is not None:
                it = int(iteration)
                comp: dict[str, Any] = {
                    "finish_reason": data.get("finish_reason"),
                    "content_chars": data.get("content_chars", 0),
                }
                usage = data.get("usage") or {}
                if usage:
                    comp["prompt_tokens"] = usage.get("prompt_tokens")
                    comp["completion_tokens"] = usage.get("completion_tokens")
                    total_prompt_tokens += usage.get("prompt_tokens") or 0
                    total_completion_tokens += usage.get("completion_tokens") or 0
                comp["latency_ms"] = data.get("latency_ms") or data.get("duration_ms")
                total_latency_ms += comp.get("latency_ms") or 0
                if data.get("finish_reason") == "length":
                    comp["truncated"] = True
                    length_truncation_count += 1
                completions[it] = comp

    # Merge starts + completions by iteration
    all_iterations = sorted(set(starts.keys()) | set(completions.keys()))
    requests: list[dict[str, Any]] = []
    for it in all_iterations:
        req: dict[str, Any] = {"iteration": it}
        if it in starts:
            req.update(starts[it])
        if it in completions:
            req.update(completions[it])
        requests.append(req)

    return {
        "request_count": len(requests),
        "length_truncation_count": length_truncation_count,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_latency_ms": total_latency_ms,
        "requests": requests,
    }


def _finalizer_diagnostics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract finalizer-specific diagnostics from runtime events."""
    finalize_forced = False
    detached_used = False
    detached_started_count = 0
    length_truncation_count = 0
    format_repair_count = 0
    schema_repair_count = 0
    final_payload_parsed = None

    for e in events:
        t = e.get("type") or ""
        data = e.get("data") or {}
        if t == "planner_finalization_forced":
            finalize_forced = True
        elif t == "llm_request_started" and data.get("force_finalize"):
            finalize_forced = True
        elif t == "planner_detached_finalizer_started":
            detached_used = True
            detached_started_count += 1
        elif t == "planner_final_output_rejected":
            format_repair_count += 1
        elif t == "planner_payload_invalid":
            schema_repair_count += 1
        elif t == "planner_final_payload_parsed":
            final_payload_parsed = data
        elif t == "llm_request_completed" and data.get("finish_reason") == "length":
            length_truncation_count += 1

    result: dict[str, Any] = {
        "force_finalize_used": finalize_forced,
        "detached_finalizer_used": detached_used,
        "detached_finalizer_started_count": detached_started_count,
        "length_truncation_count": length_truncation_count,
        "format_repair_attempt_count": format_repair_count,
        "schema_repair_attempt_count": schema_repair_count,
    }
    if final_payload_parsed:
        result["final_payload"] = final_payload_parsed
    return result


def _context_budget_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract context budget snapshots from runtime events."""
    max_estimated_chars = 0
    max_message_count = 0
    budget_warn_count = 0
    snapshots: list[dict[str, Any]] = []

    for e in events:
        data = e.get("data") or {}
        if e.get("type") == "llm_request_started":
            chars = data.get("estimated_context_chars", 0)
            msg_count = data.get("message_count", 0)
            max_estimated_chars = max(max_estimated_chars, chars)
            max_message_count = max(max_message_count, msg_count)
            if chars >= 80_000:
                budget_warn_count += 1
            snapshots.append({
                "iteration": data.get("iteration"),
                "estimated_context_chars": chars,
                "message_count": msg_count,
                "budget_action": data.get("context_budget_action"),
            })

    return {
        "max_estimated_context_chars": max_estimated_chars,
        "max_message_count": max_message_count,
        "budget_warn_count": budget_warn_count,
        "snapshots": snapshots,
    }


def _artifact_binding_summary(run: dict[str, Any] | None) -> dict[str, Any]:
    """Extract artifact binding from run data."""
    return summarize_artifact_binding(run)


def _failure_analysis(run: dict[str, Any] | None, events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Comprehensive failure analysis combining run and event data."""
    return classify_failure_mode(run, events)
