from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tools.report_evidence import missing_report_evidence_integrations


FeedbackType = Literal["hard_failure", "quality_miss"]
FeedbackSeverity = Literal["fail", "warning", "improve"]


class FeedbackItem(BaseModel):
    """Actionable feedback for an agent analysis attempt.

    hard_failure: objective errors such as code failures or missing evidence.
    quality_miss: the run completed, but the answer is too shallow or misaligned.
    """

    type: FeedbackType
    source: str
    severity: FeedbackSeverity
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    repair_instruction: str


def evaluate_attempt_feedback(
    *,
    question: str,
    report_md: str,
    execution_results: list[dict[str, Any]],
    selected_skills: list[str] | None = None,
    candidate_angles: list[dict[str, Any]] | None = None,
    chart_specs: list[dict[str, Any]] | None = None,
    caveats: list[str] | None = None,
    data_backed: bool = True,
    analysis_intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate an attempt before finalization.

    This intentionally separates two feedback classes:
    1. hard failures: code/runtime/evidence contract failures
    2. quality misses: successful run, but weak alignment/depth/actionability
    """

    items: list[FeedbackItem] = []
    report_text = report_md or ""
    lower_report = report_text.lower()
    candidate_angles = candidate_angles or []
    analysis_intent = analysis_intent or {}

    failed_steps = _unresolved_failed_steps(execution_results)
    if failed_steps:
        items.append(FeedbackItem(
            type="hard_failure",
            source="execution_result",
            severity="fail",
            message=f"{len(failed_steps)} analysis step(s) failed during code execution.",
            evidence={
                "failed_steps": [
                    {
                        "name": r.get("name"),
                        "returncode": r.get("returncode"),
                        "stderr": str(r.get("stderr", ""))[:1200],
                    }
                    for r in failed_steps[:3]
                ]
            },
            repair_instruction=(
                "Fix the failing code, re-run the affected step, and do not finalize until "
                "the repaired step returns successfully."
            ),
        ))

    table_count = sum(len(r.get("tables", []) or []) for r in execution_results)
    chart_count = sum(len(r.get("charts", []) or []) for r in execution_results)
    if data_backed and execution_results and table_count + chart_count == 0:
        items.append(FeedbackItem(
            type="hard_failure",
            source="evidence_contract",
            severity="fail",
            message="The run executed code but produced no table or chart evidence.",
            evidence={"step_count": len(execution_results), "tables": table_count, "charts": chart_count},
            repair_instruction=(
                "Run at least one evidence-producing analysis step. Save a CSV table or chart "
                "that supports the final claims."
            ),
        ))

    if data_backed and execution_results and table_count + chart_count > 0:
        missing_evidence = missing_report_evidence_integrations(
            report_md=report_text,
            execution_results=execution_results,
            chart_specs=chart_specs,
        )
        if missing_evidence:
            items.append(FeedbackItem(
                type="hard_failure",
                source="report_evidence_integration",
                severity="fail",
                message=(
                    f"{len(missing_evidence)} generated evidence artifact(s) are not "
                    "integrated into report_md."
                ),
                evidence={
                    "missing_evidence": missing_evidence[:12],
                    "table_count": table_count,
                    "chart_count": chart_count,
                },
                repair_instruction=(
                    "Regenerate report_md and evidence bindings. For every primary/supporting "
                    "table/chart, either: "
                    "(1) bind it to the relevant structured block via evidence_ids/source_refs, or "
                    "(2) integrate it inline in the related section using a compact table, concrete "
                    "numbers, or an inline chart link. "
                    "Never append a generic 'referenced charts/tables' list at the bottom of the report. "
                    "If a machine-readable anchor is needed, place a hidden evidence comment immediately "
                    "next to the related section, not at the end."
                ),
            ))

    if data_backed and not execution_results:
        items.append(FeedbackItem(
            type="hard_failure",
            source="evidence_contract",
            severity="fail",
            message="No analysis code was executed for a data-backed request.",
            evidence={"profiles_available": data_backed},
            repair_instruction="Execute code against the available dataset(s) before writing the final report.",
        ))

    if len(report_text.strip()) < 300:
        items.append(FeedbackItem(
            type="quality_miss",
            source="report_quality",
            severity="improve",
            message="The report is too short to be a useful analytical answer.",
            evidence={"report_chars": len(report_text.strip())},
            repair_instruction=(
                "Expand the report with an answer-first recommendation, key evidence, detailed findings, "
                "caveats, and next steps."
            ),
        ))

    if not _has_recommendation_section(lower_report):
        items.append(FeedbackItem(
            type="quality_miss",
            source="answer_alignment",
            severity="improve",
            message="The report does not clearly provide an answer-first recommendation or conclusion.",
            evidence={"expected_sections": ["recommendation", "conclusion", "建议", "结论"]},
            repair_instruction="Add a clear recommendation/conclusion section that directly answers the user question.",
        ))

    if data_backed and not _has_specific_numbers(report_text):
        items.append(FeedbackItem(
            type="quality_miss",
            source="evidence_strength",
            severity="improve",
            message="The report does not include enough specific quantitative evidence.",
            evidence={"tables": table_count, "charts": chart_count},
            repair_instruction=(
                "Use numbers from stdout/tables/charts in the final report. Include concrete values, "
                "comparisons, ranks, deltas, or percentages."
            ),
        ))

    if _is_open_ended_question(question) and not candidate_angles:
        items.append(FeedbackItem(
            type="quality_miss",
            source="analysis_depth",
            severity="improve",
            message="Open-ended analysis did not return candidate_angles for traceable angle selection.",
            evidence={"candidate_angle_count": 0},
            repair_instruction=(
                "Generate 3-5 candidate analysis angles, score them, select the best 2-3, "
                "and include candidate_angles in the final JSON."
            ),
        ))

    if _is_open_ended_question(question) and execution_results and len(execution_results) < 2:
        items.append(FeedbackItem(
            type="quality_miss",
            source="analysis_depth",
            severity="improve",
            message="Open-ended analysis used too few executed steps to support discovery.",
            evidence={"step_count": len(execution_results)},
            repair_instruction=(
                "Run at least one additional deep-dive step that compares dimensions, segments, "
                "drivers, trends, or anomalies."
            ),
        ))

    selected_angles = [a for a in candidate_angles if a.get("selected") is True]
    if selected_angles and len(selected_angles) > 3:
        items.append(FeedbackItem(
            type="quality_miss",
            source="angle_selection",
            severity="improve",
            message="Too many candidate angles are selected for a focused deep dive.",
            evidence={"selected_angle_count": len(selected_angles)},
            repair_instruction="Select only the top 2-3 angles and mark the others rejected with a reason.",
        ))

    incomplete_angles = [
        a for a in candidate_angles
        if not a.get("question") or not a.get("expected_evidence") or not a.get("measures")
    ]
    if candidate_angles and incomplete_angles:
        items.append(FeedbackItem(
            type="quality_miss",
            source="angle_schema",
            severity="improve",
            message="Some candidate angles are missing question, measures, or expected_evidence.",
            evidence={"incomplete_angle_count": len(incomplete_angles)},
            repair_instruction="Return complete candidate angle objects with question, dimensions, measures, expected_evidence, scores, selected, and rejected_reason.",
        ))

    if selected_angles and execution_results:
        uncovered = _uncovered_selected_angles(selected_angles, execution_results)
        if uncovered:
            items.append(FeedbackItem(
                type="quality_miss",
                source="angle_coverage",
                severity="improve",
                message="Some selected analysis angles are not visibly covered by executed steps.",
                evidence={"uncovered_angles": uncovered[:5]},
                repair_instruction=(
                    "For each selected angle, run or name an evidence-producing step that covers it. "
                    "Prefer passing angle_id to execute_code or mentioning the angle question in step_description."
                ),
            ))

    expected_output = str(analysis_intent.get("expected_output") or "")
    if expected_output in {"report", "deep_dive", "dashboard"} and chart_count == 0 and data_backed:
        items.append(FeedbackItem(
            type="hard_failure",
            source="visual_evidence",
            severity="fail",
            message=(
                f"Intent expects a {expected_output} visual deliverable, but no chart evidence "
                "was produced."
            ),
            evidence={"expected_output": expected_output, "chart_count": chart_count},
            repair_instruction=(
                "Produce at least one decision-relevant trend, comparison, composition, or "
                "distribution chart, save it with a relative filename, and cite it in the core conclusion."
            ),
        ))

    primary_metrics = [str(m).lower() for m in analysis_intent.get("primary_metrics") or []]
    if primary_metrics and not any(metric in lower_report for metric in primary_metrics[:4]):
        items.append(FeedbackItem(
            type="quality_miss",
            source="intent_alignment",
            severity="improve",
            message="The report does not reference the primary metrics inferred from the user request.",
            evidence={"primary_metrics": analysis_intent.get("primary_metrics")},
            repair_instruction="Ground the report around the inferred primary metrics or explain why they were not usable.",
        ))

    hard_failures = [i for i in items if i.type == "hard_failure"]
    quality_misses = [i for i in items if i.type == "quality_miss"]
    quality_score = _quality_score(items)

    return {
        "passed": not hard_failures and quality_score >= 0.72,
        "should_retry": bool(hard_failures) or quality_score < 0.72,
        "hard_failure_count": len(hard_failures),
        "quality_miss_count": len(quality_misses),
        "quality_score": quality_score,
        "items": [i.model_dump(mode="json") for i in items],
        "summary": summarize_feedback_for_llm([i.model_dump(mode="json") for i in items]),
    }


def summarize_feedback_for_llm(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Feedback evaluation passed. No repair needed."

    hard = [i for i in items if i.get("type") == "hard_failure"]
    quality = [i for i in items if i.get("type") == "quality_miss"]
    lines = ["The previous attempt needs another iteration before finalizing.", ""]

    if hard:
        lines.append("## Hard failure feedback: fix errors first")
        for item in hard[:6]:
            lines.append(f"- {item.get('message')}")
            lines.append(f"  Repair: {item.get('repair_instruction')}")
        lines.append("")

    if quality:
        lines.append("## Quality feedback: run succeeded but did not meet expectations")
        for item in quality[:6]:
            lines.append(f"- {item.get('message')}")
            lines.append(f"  Improve: {item.get('repair_instruction')}")
        lines.append("")

    lines.extend([
        "Do not just restate the previous answer.",
        "Preserve valid evidence, but re-run or add analysis steps where needed.",
        "Return the final JSON only after hard failures are fixed and quality feedback is addressed.",
    ])
    return "\n".join(lines)


def _quality_score(items: list[FeedbackItem]) -> float:
    score = 1.0
    for item in items:
        if item.type == "hard_failure":
            score -= 0.45
        elif item.type == "quality_miss":
            score -= 0.14
    return max(0.0, round(score, 2))


def _unresolved_failed_steps(
    execution_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    for result in execution_results:
        name = _base_step_name(str(result.get("name") or ""))
        latest_by_step[name] = result
        repair_of = _base_step_name(str(result.get("repair_of") or ""))
        if repair_of and result.get("returncode") in (0, None) and result.get("status") != "failed":
            latest_by_step[repair_of] = result
    return [
        result
        for result in latest_by_step.values()
        if result.get("returncode") not in (0, None) or result.get("status") == "failed"
    ]


def _base_step_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        return ""
    section_match = re.match(r"^(section\s+[a-z0-9]+)\s*[:：]", normalized, re.IGNORECASE)
    if section_match:
        return section_match.group(1).lower()
    normalized = re.sub(
        r"[\s_（(]*(repaired|fixed|optimized|修正版|优化版|修复版|重试版|v\d+)[）)]*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.lower()


def _has_recommendation_section(lower_report: str) -> bool:
    return any(token in lower_report for token in ["recommendation", "conclusion", "建议", "结论", "recommend"])


def _has_specific_numbers(report: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|pct|个|次|元|万|k|m|million|billion)?\b", report, re.I))


def _is_open_ended_question(question: str) -> bool:
    q = question.lower()
    triggers = [
        "分析", "看看", "发现", "洞察", "有什么", "机会", "问题", "异常", "趋势",
        "analyze", "analysis", "insight", "explore", "discover", "what can", "anything interesting",
    ]
    return any(t in q for t in triggers)


def _uncovered_selected_angles(
    selected_angles: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
) -> list[dict[str, str]]:
    step_texts = []
    for result in execution_results:
        step_texts.append(
            " ".join(
                str(part or "")
                for part in (
                    result.get("angle_id"),
                    result.get("name"),
                    result.get("description"),
                    result.get("stdout"),
                )
            ).lower()
        )
    combined = "\n".join(step_texts)

    uncovered: list[dict[str, str]] = []
    for angle in selected_angles:
        angle_id = str(angle.get("id") or "").lower()
        question = str(angle.get("question") or "")
        tokens = _tokens(question)
        measures = [str(m).lower() for m in angle.get("measures") or []]
        covered = False
        if angle_id and angle_id in combined:
            covered = True
        elif tokens and any(len(tokens & _tokens(step_text)) >= min(2, len(tokens)) for step_text in step_texts):
            covered = True
        elif measures and any(measure and measure in combined for measure in measures):
            covered = True
        if not covered:
            uncovered.append({"id": angle_id, "question": question[:160]})
    return uncovered


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff_]+", text.lower()) if len(token) >= 2}
