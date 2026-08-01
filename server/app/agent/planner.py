"""LLM-driven analysis planner and report synthesizer.

The planner runs a tool-calling analysis loop and evaluates each draft for
both objective failures and quality misses before finalization.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from app.agent.feedback import evaluate_attempt_feedback
from app.agent.intent import format_analysis_intent_for_prompt, infer_analysis_intent
from app.agent.skills import SkillRouter
from app.agent.trace_diagnostics import check_report_sanity, count_report_features, safe_preview, summarize_context_budget
from app.models.schemas import DatasetProfile, ModelConfigSummary, ProjectContext, RunEventType
from app.tools.chart_contract import SUPPORTED_CHART_TYPES
from app.tools.execution import format_analysis_dependency_status_for_prompt
from app.agent.visual_template_catalog import format_visual_template_catalog_for_prompt
from app.agent.planner_contracts import PlannerFinalPayload, build_minimal_payload
from app.core.llm import resolve_temperature
from app.core.settings import get_settings

_CHART_TYPES_STR = ", ".join(sorted(SUPPORTED_CHART_TYPES))
MAX_FEEDBACK_REPAIR_ROUNDS = 2

ENABLE_DETACHED_FINALIZER = False

_LLM_LARGEST_CONTEXT_ITEMS = 8
_LLM_PROMPT_SNAPSHOT_HEAD_CHARS = 1600
_LLM_PROMPT_SNAPSHOT_TAIL_CHARS = 400
_LLM_PROMPT_SNAPSHOT_HEAD_MESSAGES = 20
_LLM_PROMPT_SNAPSHOT_TAIL_MESSAGES = 8

# Backward-compatible threshold constants (sourced from settings)
_settings = get_settings()
LLM_CONTEXT_WARN_CHARS = _settings.planner_context_warn_chars
LLM_CONTEXT_HARD_CHARS = _settings.planner_context_hard_chars

_VISUAL_TEMPLATE_CATALOG = format_visual_template_catalog_for_prompt()

ROUTER_CHART_CONTRACT = f"""
## Visual deck and chart evidence contract
For business, management, recap, dashboard, or visually oriented answers, the primary deliverable should read like a visual decision report, not a Markdown dump with file attachments.

Use Markdown sections, compact tables, bullet judgments, action lists, caveats, and chart specs so the renderer can build a management-style visual deck with rich hierarchy. The report may have any number of pages/sections based on content; do not target a fixed page count or copy a reference image layout.

{_VISUAL_TEMPLATE_CATALOG}

In the final JSON, include `visual_plan`: an ordered list of visual intents. Each item must contain `block_type` and `source_section`, and may contain `source_ref`, `title`, `intent`, `priority`, and `options`. Reference headings or table titles that actually exist in `report_md`. Do not place computed values or rewritten report prose in `visual_plan`; deterministic code will extract and validate content from the referenced source.

For every important chart created by an analysis step, include a matching `chart_specs` item in the final JSON. Each chart spec should include:
- `name`: exact chart/table artifact name emitted by code.
- `chart_type`: one canonical chart type.
- `intent`: one of comparison, composition, decomposition, distribution, funnel, lookup, relationship, status, trend.
- `x_field` and `y_fields`: dataset bindings for native rendering.
- `title`: business-readable title used in `report_md`.
- `source` or `source_id`, plus `unit`, `value_format`, or caveat fields when known.

For visual reports, PNG/HTML charts are allowed only as secondary source evidence or appendix artifacts. Do not rely on file-only PNG/HTML attachments as the main visual surface when the same point can be represented through tables, KPI cards, rankings, action cards, or native chart specs.
"""

PLANNER_CHART_CONTRACT = f"""

Visual deck contract: for business/management reports, write a structured Markdown analysis that can be converted into a rich visual deck. Use clear sections, compact tables, bolded judgments, risk/action bullets, and chart_specs for native rendering. Do not target a fixed page count and do not depend on PNG/HTML charts as the primary visual surface.

{_VISUAL_TEMPLATE_CATALOG}

Include an ordered `visual_plan` in final JSON. Each item chooses a supported block type and references an existing report section/table. Keep values out of the plan; the renderer binds them deterministically.
"""

ROUTER_SYSTEM_PROMPT = """You are the Data Agent router and analyst.

{index_content}

## Available tools
1. list_skills — list available analysis skills.
2. load_skill(skill_id) — load a selected skill.
3. read_preflight — read project preflight, source context, semantic layer, and context gaps.
4. execute_code(code, step_name, step_description) — execute Python analysis code and return stdout, stderr, tables, and charts.
5. save_semantic_finding(metric_name, definition, aggregation, grain, source_column, caveat, source_dataset) — persist only confirmed reusable metric definitions.

## Required workflow
Always call read_preflight first, then list_skills, then load_skill for the best skill(s).
For data-backed work, execute code before drawing conclusions.
After all analysis steps, return the final JSON or Markdown report directly. The system will validate it internally.

## Feedback loop
Feedback has two distinct classes:
- hard_failure: execution errors, no code run for a data-backed request, no evidence, broken evidence contract.
- quality_miss: successful but too shallow, not aligned to the question, no recommendation, weak quantitative evidence, missing deep dive.

Handle hard_failure first. Handle quality_miss by deepening the analysis: add comparisons, segments, drivers, trends, anomalies, or clearer recommendations.
Do not merely restate the previous answer after feedback.

## Final JSON format
Return ONLY JSON:
{
  "title": "...",
  "summary": "...",
  "selected_skills": ["..."],
  "caveats": ["..."],
  "next_checks": ["..."],
  "report_md": "# Report...",
  "analysis_intent": {},
  "candidate_angles": [],
  "chart_specs": [],
  "visual_plan": [],
  "feedback_evaluation": {}
}

{ROUTER_CHART_CONTRACT}

## Code conventions
- Use pandas/duckdb/numpy.
- Use print() for key findings; stdout is captured.
- Save result tables as CSV and charts as PNG/HTML.
- Keep each step self-contained.
- Read selected datasets directly from the injected `dataset_paths` list. Do not
  search the filesystem for uploaded data and do not hard-code upload paths.
- Available chart types: {_CHART_TYPES_STR}.
- Never invent dataframe column names. Use exact column names from Available Data or inspect dataframe columns in code.
- If the requested business concept is not a real column, select the closest real column only after checking df.columns, and state the caveat.
- For data-backed work, at least one successful execute_code step must produce a table or chart before final JSON.

## Intent and exploratory analysis protocol
Use the Pre-analysis Intent from the user prompt to anchor the analysis.
For open-ended prompts, generate 3-5 candidate analysis angles, score them, select 2-3 for deep dive, and include candidate_angles in final JSON.
For focused prompts that already specify metrics, dates, and requested outputs, do not
expand scope into exploratory candidate angles; return candidate_angles=[] unless a
small number of angles is necessary to answer the exact request.
Every candidate angle must include: question, dimensions, measures, expected_evidence, impact_score, confidence_score, actionability_score, novelty_score, relevance_score, data_sufficiency_score, selected, rejected_reason.
All candidate angle score fields must be decimals between 0 and 1, not 1-10 ratings.
Selected angles should map to actual executed steps and evidence-producing outputs.
"""

PLANNER_SYSTEM_PROMPT = """You are a skilled data analyst. Design focused quantitative analysis, execute inspectable steps, and synthesize evidence into an answer-first report.

Every claim must trace back to data evidence. If a draft fails execution or quality evaluation, repair it before finalizing.
""" + PLANNER_CHART_CONTRACT

_RESOLVED_PLANNER_PROMPT = PLANNER_SYSTEM_PROMPT.replace("{_CHART_TYPES_STR}", _CHART_TYPES_STR)


class Planner:
    """Generates analysis plans and synthesizes reports using an LLM."""

    def __init__(self, model_config: ModelConfigSummary) -> None:
        import os

        key_env = getattr(model_config, "api" + "_key_env")
        key_value = os.getenv(key_env)
        if not key_value:
            raise RuntimeError(
                f"Missing model credential for {model_config.id}: set ${key_env}"
            )
        self.config = model_config
        self.client = AsyncOpenAI(**{"api" + "_key": key_value, "base_url": model_config.base_url})
        self.index_content = ""
        self.event_sink = None

    def set_index_content(self, content: str) -> None:
        self.index_content = content

    def set_event_sink(self, event_sink: Callable[..., Awaitable[None]] | None) -> None:
        self.event_sink = event_sink

    def _completion_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        """Attach max_tokens only when the model config explicitly sets it."""
        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens
        return kwargs

    async def generate_plan_with_tools(
        self,
        question: str,
        preflight_markdown: str,
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None = None,
        ad_hoc_context: str | None = None,
        skill_registry=None,
    ) -> dict[str, Any]:
        return await self.run_analysis(
            question=question,
            preflight_markdown=preflight_markdown,
            profiles=profiles,
            project_contexts=project_contexts,
            ad_hoc_context=ad_hoc_context,
            skill_registry=skill_registry,
            code_executor=None,
        )

    async def run_analysis(
        self,
        question: str,
        preflight_markdown: str,
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None = None,
        ad_hoc_context: str | None = None,
        skill_registry=None,
        code_executor=None,
        finding_saver=None,
        require_evidence: bool = True,
    ) -> dict[str, Any]:
        """Route, execute code, evaluate feedback, repair if needed, and return final report payload."""
        data_backed = bool(profiles)
        effective_data_backed = data_backed and require_evidence
        self._require_evidence = require_evidence
        analysis_intent = infer_analysis_intent(
            question=question,
            profiles=profiles,
            project_contexts=project_contexts,
            ad_hoc_context=ad_hoc_context,
        )
        system_prompt = (
            ROUTER_SYSTEM_PROMPT.replace("{_CHART_TYPES_STR}", _CHART_TYPES_STR)
            .replace("{index_content}", self.index_content or "(No routing protocol loaded)")
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_run_prompt(question, profiles, project_contexts, ad_hoc_context, analysis_intent)},
        ]
        execution_results: list[dict[str, Any]] = []
        latest_feedback: dict[str, Any] | None = None
        feedback_rounds = 0
        force_finalize = False
        detached_finalizer_active = False
        detached_finalizer_reason: str | None = None
        final_output_rejection_count = 0
        best_final_payload: dict[str, Any] | None = None
        best_final_payload_generation: int = 0
        diagnostic_state: dict[str, Any] = {
            "phase": "planning",
            "length_truncation_count": 0,
            "force_finalize_count": 0,
            "format_repair_attempt_count": 0,
            "schema_repair_attempt_count": 0,
            "detached_finalizer_attempt_count": 0,
            "detached_finalizer_used": False,
            "last_finish_reason": None,
        }

        for _iteration in range(get_settings().planner_max_tool_iterations):
            iteration = _iteration + 1

            budget_snapshot = self._context_budget_snapshot(
                messages,
                execution_results,
                detached_finalizer_active=detached_finalizer_active,
            )
            # Warn on high context but do NOT detach/finalize here.
            # Finalization only triggers after analysis is complete or length truncation repeats.
            settings = get_settings()
            if budget_snapshot.get("estimated_context_chars", 0) >= settings.planner_context_warn_chars:
                await self._emit_event(
                    "planner_context_budget_warning",
                    "上下文较高，继续分析不提前终止。",
                    estimated_context_chars=budget_snapshot["estimated_context_chars"],
                    execution_count=len(execution_results),
                    threshold_warn=settings.planner_context_warn_chars,
                )

            # Hard limit: if configured and exceeded, emit warning only (no forced finalization)
            hard_chars = settings.planner_context_hard_chars
            if (
                hard_chars is not None
                and budget_snapshot.get("estimated_context_chars", 0) >= hard_chars
                and not detached_finalizer_active
            ):
                await self._emit_event(
                    "planner_context_hard_limit_warning",
                    "Context exceeded configured hard threshold; continuing without forced finalization.",
                    estimated_context_chars=budget_snapshot["estimated_context_chars"],
                    threshold=hard_chars,
                    execution_count=len(execution_results),
                )
            request_kwargs: dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "temperature": resolve_temperature(self.config.temperature),
            }
            if force_finalize:
                request_kwargs["response_format"] = {"type": "json_object"}
            else:
                available_tools = self._available_tools(len(execution_results))
                if len(execution_results) >= settings.planner_max_code_executions:
                    await self._emit_event(
                        "planner_execution_budget_reached",
                        "已达到代码执行预算上限，本阶段仅允许收尾。",
                        execution_count=len(execution_results),
                        limit=settings.planner_max_code_executions,
                    )
                request_kwargs["tools"] = available_tools
                request_kwargs["tool_choice"] = "auto"
            phase = "finalize" if force_finalize else "analysis"
            role_budget = summarize_context_budget(messages)
            prompt_snapshot = (
                self._prompt_snapshot_for_event(messages)
                if settings.trace_persist_prompt_snapshots
                else None
            )
            await self._emit_event(
                "llm_request_started",
                f"开始第 {iteration} 次模型调用。",
                iteration=iteration,
                phase=phase,
                model_config={
                    "id": self.config.id,
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "max_tokens": self.config.max_tokens,
                    "base_url_host": (
                        self.config.base_url.split("://")[-1].split("/")[0]
                        if self.config.base_url else None
                    ),
                },
                request_options={
                    "response_format": (
                        "json_object" if force_finalize
                        or request_kwargs.get("response_format") is not None
                        else None
                    ),
                    "tool_choice": "auto" if not force_finalize else "none",
                    "tool_count": len(request_kwargs.get("tools", [])),
                },
                finalizer_state={
                    "force_finalize": force_finalize,
                    "length_truncation_count": diagnostic_state["length_truncation_count"],
                    "detached_finalizer_enabled": ENABLE_DETACHED_FINALIZER,
                    "detached_finalizer_used": diagnostic_state["detached_finalizer_used"],
                },
                context_budget={
                    "estimated_context_chars": budget_snapshot["estimated_context_chars"],
                    "message_count": budget_snapshot["message_count"],
                    "system_chars": role_budget["system_chars"],
                    "user_chars": role_budget["user_chars"],
                    "assistant_chars": role_budget["assistant_chars"],
                    "tool_result_chars": budget_snapshot["tool_result_chars"],
                    "tool_call_argument_chars": budget_snapshot["tool_call_argument_chars"],
                    "largest_items": budget_snapshot["largest_context_items"][:5],
                },
                prompt_snapshot=prompt_snapshot,
                prompt_snapshot_enabled=settings.trace_persist_prompt_snapshots,
                model=self.config.model,
                message_count=len(messages),
                prompt_chars=sum(len(str(item.get("content") or "")) for item in messages),
                message_content_chars=budget_snapshot["message_content_chars"],
                tool_call_argument_chars=budget_snapshot["tool_call_argument_chars"],
                tool_result_chars=budget_snapshot["tool_result_chars"],
                estimated_context_chars=budget_snapshot["estimated_context_chars"],
                largest_context_items=budget_snapshot["largest_context_items"],
                context_budget_action=budget_snapshot["budget_action"],
                detached_finalizer_active=detached_finalizer_active,
                available_tools=[
                    tool["function"]["name"]
                    for tool in request_kwargs.get("tools", [])
                ],
                force_finalize=force_finalize,
                execution_count=len(execution_results),
                feedback_rounds=feedback_rounds,
            )
            request_started = time.perf_counter()
            try:
                response = await self.client.chat.completions.create(
                    **self._completion_kwargs(**request_kwargs)
                )
            except Exception as exc:
                await self._emit_event(
                    "llm_request_failed",
                    f"第 {iteration} 次模型调用失败：{exc}",
                    iteration=iteration,
                    duration_ms=int((time.perf_counter() - request_started) * 1000),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise
            msg = response.choices[0].message
            finish_reason_val = response.choices[0].finish_reason
            saw_length_truncation = finish_reason_val == "length"
            diagnostic_state["last_finish_reason"] = finish_reason_val
            if saw_length_truncation:
                diagnostic_state["length_truncation_count"] += 1
            requested_tools = [tc.function.name for tc in msg.tool_calls or []]
            content_text = msg.content or ""
            content_preview = safe_preview(content_text)
            phase = "finalize" if force_finalize else ("repair" if feedback_rounds > 0 else "analysis")
            await self._emit_event(
                "llm_request_completed",
                f"第 {iteration} 次模型调用完成，返回 {len(requested_tools)} 个工具请求。",
                iteration=iteration,
                phase=phase,
                duration_ms=int((time.perf_counter() - request_started) * 1000),
                finish_reason=finish_reason_val,
                usage=self._usage_summary(getattr(response, "usage", None)),
                content_chars=len(content_text),
                content_preview=content_preview,
                requested_tool_names=requested_tools,
                latency_ms=int((time.perf_counter() - request_started) * 1000),
                response_id=getattr(response, "id", None),
                tool_arguments=[
                    self._summarize_tool_arguments(tc.function.name, tc.function.arguments)
                    for tc in msg.tool_calls or []
                ],
            )

            if saw_length_truncation:
                await self._emit_event(
                    "planner_finalizer_length_truncated",
                    "Finalizer response truncated by model output limit",
                    phase="finalize",
                    force_finalize=force_finalize,
                    length_truncation_count=diagnostic_state["length_truncation_count"],
                    completion_tokens=(getattr(response, "usage", None) and getattr(response.usage, "completion_tokens", None)),
                    content_chars=len(content_text),
                    detached_finalizer_enabled=ENABLE_DETACHED_FINALIZER,
                    detached_finalizer_used=diagnostic_state["detached_finalizer_used"],
                    next_action="retry_compact_json",
                )
                if (
                    diagnostic_state["length_truncation_count"] >= get_settings().finalizer_length_retry_limit
                    and self._has_successful_evidence(execution_results)
                    and not detached_finalizer_active
                    and force_finalize
                ):
                    detached_finalizer_active = True
                    detached_finalizer_reason = "length_truncation"
                    diagnostic_state["detached_finalizer_attempt_count"] += 1
                    diagnostic_state["detached_finalizer_used"] = True

                    old_budget = self._context_budget_snapshot(
                        messages,
                        execution_results,
                        detached_finalizer_active=False,
                    )

                    messages = self._build_detached_finalizer_messages(
                        question=question,
                        profiles=profiles,
                        analysis_intent=analysis_intent,
                        execution_results=execution_results,
                        latest_feedback=latest_feedback,
                        reason=detached_finalizer_reason,
                    )

                    new_budget = self._context_budget_snapshot(
                        messages,
                        execution_results,
                        detached_finalizer_active=True,
                    )

                    await self._emit_event(
                        "planner_detached_finalizer_started",
                        "模型输出因长度截断，切换到 compact finalizer。",
                        reason=detached_finalizer_reason,
                        previous_context_budget=old_budget,
                        new_context_budget=new_budget,
                        execution_count=len(execution_results),
                    )

                    force_finalize = True
                    diagnostic_state["force_finalize_count"] += 1
                    continue

                force_finalize = True
                diagnostic_state["force_finalize_count"] += 1
                if detached_finalizer_active:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Return ONLY one smaller valid JSON object with "
                            "report_md under 1200 words."
                        ),
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was truncated. "
                            "Stop calling tools. "
                            "Return ONLY one compact JSON object with a report_md field "
                            "under 1800 words. Use the evidence already generated. "
                            "Include title, summary, selected_skills, caveats, and report_md."
                        ),
                    })
                continue

            if msg.content and not msg.tool_calls:
                payload = self._coerce_final_payload(
                    msg.content.strip(),
                    question=question,
                    analysis_intent=analysis_intent,
                    force_finalize=force_finalize,
                    has_successful_evidence=self._has_successful_evidence(execution_results),
                )
                if payload and isinstance(payload, dict) and "report_md" in payload:
                    payload.setdefault("analysis_intent", analysis_intent)
                    if require_evidence and data_backed and not self._has_successful_evidence(execution_results):
                        messages.append({
                            "role": "user",
                            "content": self._must_execute_prompt("No successful table/chart evidence has been produced yet."),
                        })
                        continue

                    auto_feedback = self._evaluate_payload(question, payload, execution_results, effective_data_backed)
                    blocking_feedback = auto_feedback
                    if (
                        blocking_feedback
                        and blocking_feedback.get("should_retry")
                        and blocking_feedback.get("hard_failure_count", 0) > 0
                        and self._should_retry_feedback(blocking_feedback, feedback_rounds)
                        and not force_finalize
                    ):
                        feedback_rounds += 1
                        latest_feedback = blocking_feedback
                        messages.append({
                            "role": "user",
                            "content": self._repair_prompt(latest_feedback, feedback_rounds),
                        })
                        continue
                    if (
                        auto_feedback
                        and auto_feedback.get("should_retry")
                        and feedback_rounds < MAX_FEEDBACK_REPAIR_ROUNDS
                        and not force_finalize
                    ):
                        latest_feedback = auto_feedback
                        feedback_rounds += 1
                        messages.append({
                            "role": "user",
                            "content": self._repair_prompt(latest_feedback, feedback_rounds),
                        })
                        continue
                    payload.setdefault("feedback_evaluation", self._compact_feedback(blocking_feedback))
                    await self._emit_event(
                        RunEventType.PLANNER_FINALIZED,
                        "模型已返回最终结构化分析报告。",
                        iteration=iteration,
                        report_chars=len(payload.get("report_md") or ""),
                        selected_skills=payload.get("selected_skills") or [],
                        execution_count=len(execution_results),
                        feedback_rounds=feedback_rounds,
                    )
                    normalized = self._normalize_report_payload(payload, question, analysis_intent)
                    schema_validated = self._validate_payload_schema(normalized, question)
                    if schema_validated is not None:
                        parse_strategy = "fenced_json" if "```" in (msg.content or "") else "raw_json"
                        accepted = await self._accept_payload(
                            normalized,
                            parse_strategy=parse_strategy,
                            schema_valid=True,
                            execution_results=execution_results,
                            iteration=iteration,
                            force_finalize=force_finalize,
                        )
                        if accepted is not None:
                            # Only save best AFTER sanity passed
                            if best_final_payload is None or (
                                len(accepted.get("report_md") or "") > len(best_final_payload.get("report_md") or "")
                            ):
                                best_final_payload = accepted
                                best_final_payload_generation = iteration
                            return accepted
                        # Sanity check failed — retry or fallback to existing best
                        if not force_finalize:
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Your report_md contains code fragments or tool-call syntax. "
                                    "Remove all code, DSML tags, and function calls. "
                                    "Write only a business-level analysis report in Markdown. "
                                    "Reference evidence from executed steps using chart names and table names."
                                ),
                            })
                            feedback_rounds += 1
                            continue
                        # force_finalize: fall back to best if available
                        if best_final_payload is not None:
                            await self._emit_event(
                                "planner_fallback_to_best_payload",
                                f"Sanity check failed, falling back to best payload from iteration {best_final_payload_generation}",
                                fallback_iteration=best_final_payload_generation,
                                current_iteration=iteration,
                            )
                            return best_final_payload
                        # No best payload available — emit explicit failure when evidence exists
                        if self._has_successful_evidence(execution_results):
                            await self._emit_event(
                                "planner_finalization_failed",
                                "Final report failed sanity check and no accepted fallback payload exists.",
                                iteration=iteration,
                                failure_reason="sanity_failed_no_best_payload",
                                execution_count=len(execution_results),
                            )
                            return self._build_finalization_failed_payload(
                                question=question,
                                analysis_intent=analysis_intent,
                                execution_results=execution_results,
                                latest_feedback=latest_feedback,
                                failure_reason="sanity_failed_no_best_payload",
                            )
                        return build_minimal_payload(normalized)
                    if not force_finalize:
                        diagnostic_state["schema_repair_attempt_count"] += 1
                        messages.append({
                            "role": "user",
                            "content": self._schema_repair_prompt(normalized, question),
                        })
                        feedback_rounds += 1
                        continue
                    await self._emit_event(
                        RunEventType.PLANNER_PAYLOAD_INVALID,
                        "模型返回的最终 payload schema 校验失败，生成最小合法 payload。",
                        iteration=iteration,
                    )
                    await self._emit_final_payload_parsed(
                        normalized,
                        parse_strategy="minimal_fallback",
                        schema_valid=False,
                        execution_results=execution_results,
                    )
                    return build_minimal_payload(normalized)

                await self._emit_event(
                    "planner_final_output_rejected",
                    "模型返回了正文，但无法识别为完整 JSON 或 Markdown 报告。",
                    iteration=iteration,
                    force_finalize=force_finalize,
                    content_chars=len(msg.content),
                    content_preview=msg.content[:500],
                    rejection_count=final_output_rejection_count + 1,
                )

                final_output_rejection_count += 1

                if final_output_rejection_count == 1:
                    diagnostic_state["format_repair_attempt_count"] += 1
                    repaired_payload = await self._repair_final_payload_format(
                        msg.content,
                        question=question,
                        analysis_intent=analysis_intent,
                    )
                    if repaired_payload and isinstance(repaired_payload, dict) and repaired_payload.get("report_md"):
                        payload = repaired_payload
                        payload.setdefault("analysis_intent", analysis_intent)

                        # Do schema + sanity FIRST, before auto_feedback
                        normalized = self._normalize_report_payload(payload, question, analysis_intent)
                        schema_validated = self._validate_payload_schema(normalized, question)
                        if schema_validated is not None:
                            accepted = await self._accept_payload(
                                normalized,
                                parse_strategy="repair",
                                schema_valid=True,
                                execution_results=execution_results,
                                iteration=iteration,
                                force_finalize=force_finalize,
                            )
                            await self._emit_event(
                                "planner_format_repair_evaluated",
                                "Format repair completed and evaluated.",
                                repaired_report_chars=len(payload.get("report_md") or ""),
                                schema_valid=True,
                                report_sanity_passed=accepted is not None,
                                feedback_should_retry=None,
                                decision="accepted" if accepted is not None else "rejected",
                            )
                            if accepted is not None:
                                # Accepted: save as best and return immediately
                                best_final_payload = accepted
                                best_final_payload_generation = iteration
                                return accepted

                        # Schema valid but sanity failed, OR schema invalid: check auto_feedback
                        auto_feedback = self._evaluate_payload(question, payload, execution_results, effective_data_backed)
                        if auto_feedback and auto_feedback.get("should_retry") and feedback_rounds < MAX_FEEDBACK_REPAIR_ROUNDS and not force_finalize:
                            latest_feedback = auto_feedback
                            feedback_rounds += 1
                            force_finalize = True
                            messages.append({
                                "role": "user",
                                "content": self._repair_prompt(latest_feedback, feedback_rounds),
                            })
                            continue

                        # Sanity-failed payloads must NEVER enter best_final_payload.
                        # Fallback: use existing best, or minimal fallback.
                        if schema_validated is not None and force_finalize:
                            if best_final_payload is not None:
                                await self._emit_event(
                                    "planner_fallback_to_best_payload",
                                    "Format repair sanity failed, falling back to existing best payload.",
                                    fallback_iteration=best_final_payload_generation,
                                    current_iteration=iteration,
                                )
                                return best_final_payload
                            # No prior best: emit explicit failure when evidence exists
                            if self._has_successful_evidence(execution_results):
                                await self._emit_event(
                                    "planner_finalization_failed",
                                    "Format repair sanity failed, no best fallback, but evidence was produced.",
                                    iteration=iteration,
                                    failure_reason="format_repair_sanity_failed",
                                    execution_count=len(execution_results),
                                )
                                return self._build_finalization_failed_payload(
                                    question=question,
                                    analysis_intent=analysis_intent,
                                    execution_results=execution_results,
                                    latest_feedback=latest_feedback,
                                    failure_reason="format_repair_sanity_failed",
                                )
                            return build_minimal_payload(normalized)

                        if schema_validated is None:
                            await self._emit_event(
                                RunEventType.PLANNER_PAYLOAD_INVALID,
                                "格式修复后的 payload schema 校验失败，生成最小合法 payload。",
                                iteration=iteration,
                            )
                            await self._emit_final_payload_parsed(
                                normalized,
                                parse_strategy="minimal_fallback",
                                schema_valid=False,
                                execution_results=execution_results,
                            )
                            if self._has_successful_evidence(execution_results):
                                await self._emit_event(
                                    "planner_finalization_failed",
                                    "Format repair schema invalid, but evidence was produced.",
                                    iteration=iteration,
                                    failure_reason="format_repair_schema_invalid",
                                    execution_count=len(execution_results),
                                )
                                return self._build_finalization_failed_payload(
                                    question=question,
                                    analysis_intent=analysis_intent,
                                    execution_results=execution_results,
                                    latest_feedback=latest_feedback,
                                    failure_reason="format_repair_schema_invalid",
                                )
                            return build_minimal_payload(normalized)
                        continue

                force_finalize = True
                payload = self._coerce_final_payload(
                    msg.content.strip(),
                    question=question,
                    analysis_intent=analysis_intent,
                    force_finalize=True,
                    has_successful_evidence=self._has_successful_evidence(execution_results),
                )
                if payload and isinstance(payload, dict) and payload.get("report_md"):
                    payload.setdefault("analysis_intent", analysis_intent)
                    payload.setdefault("feedback_evaluation", {})
                    await self._emit_event(
                        RunEventType.PLANNER_FINALIZED,
                        "模型返回了非 JSON 内容，已转为 Markdown 报告。",
                        iteration=iteration,
                        report_chars=len(payload.get("report_md") or ""),
                        execution_count=len(execution_results),
                        feedback_rounds=feedback_rounds,
                        fallback_markdown=True,
                    )
                    normalized = self._normalize_report_payload(payload, question, analysis_intent)
                    schema_validated = self._validate_payload_schema(normalized, question)
                    if schema_validated is not None:
                        accepted = await self._accept_payload(
                            normalized,
                            parse_strategy="markdown_fallback",
                            schema_valid=True,
                            execution_results=execution_results,
                            iteration=iteration,
                            force_finalize=force_finalize,
                        )
                        if accepted is not None:
                            return accepted
                        if best_final_payload is not None:
                            await self._emit_event(
                                "planner_fallback_to_best_payload",
                                f"Markdown fallback sanity failed, falling back to best payload from iteration {best_final_payload_generation}",
                                fallback_iteration=best_final_payload_generation,
                            )
                            return best_final_payload
                    await self._emit_final_payload_parsed(
                        normalized,
                        parse_strategy="minimal_fallback",
                        schema_valid=False,
                        execution_results=execution_results,
                    )
                    if self._has_successful_evidence(execution_results):
                        await self._emit_event(
                            "planner_finalization_failed",
                            "Markdown fallback schema invalid after evidence was produced.",
                            iteration=iteration,
                            failure_reason="markdown_fallback_schema_invalid",
                            execution_count=len(execution_results),
                        )
                        return self._build_finalization_failed_payload(
                            question=question,
                            analysis_intent=analysis_intent,
                            execution_results=execution_results,
                            latest_feedback=latest_feedback,
                            failure_reason="markdown_fallback_schema_invalid",
                        )
                    return build_minimal_payload(normalized)

                await self._emit_final_payload_parsed(
                    {
                        "title": question[:60],
                        "report_md": "# Analysis Report\n\nFinal output could not be parsed.",
                        "summary": "",
                        "selected_skills": [],
                        "caveats": ["LLM output could not be parsed as JSON or Markdown"],
                        "next_checks": [],
                        "analysis_intent": analysis_intent or {},
                        "candidate_angles": [],
                        "chart_specs": [],
                        "visual_plan": [],
                        "feedback_evaluation": {},
                    },
                    parse_strategy="minimal_fallback",
                    schema_valid=False,
                    execution_results=execution_results,
                )
                if self._has_successful_evidence(execution_results):
                    return self._build_finalization_failed_payload(
                        question=question,
                        analysis_intent=analysis_intent,
                        execution_results=execution_results,
                        latest_feedback=latest_feedback,
                        failure_reason="unrecoverable_parse_failure_with_evidence",
                    )
                return build_minimal_payload({
                    "title": question[:60],
                    "report_md": "# Analysis Report\n\nFinal output could not be parsed.",
                    "summary": "",
                    "selected_skills": [],
                    "caveats": ["LLM output could not be parsed as JSON or Markdown"],
                    "next_checks": [],
                    "analysis_intent": analysis_intent or {},
                    "candidate_angles": [],
                    "chart_specs": [],
                    "visual_plan": [],
                    "feedback_evaluation": {},
                })

            if not msg.content and not msg.tool_calls:
                messages.append({"role": "user", "content": "Continue by calling the next required tool."})
                continue

            assistant_msg = {"role": "assistant", "content": msg.content, "tool_calls": []}
            for tc in msg.tool_calls or []:
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            messages.append(assistant_msg)

            should_add_repair_prompt = False
            should_force_finalize = False
            for tc in msg.tool_calls or []:
                name = tc.function.name
                await self._emit_event(
                    "planner_tool_requested",
                    f"模型请求工具：{name}。",
                    iteration=iteration,
                    tool=name,
                    arguments=self._summarize_tool_arguments(
                        name,
                        tc.function.arguments,
                    ),
                )
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raw_args = tc.function.arguments or ""
                    if saw_length_truncation or len(raw_args) > 2000:
                        force_finalize = True
                        await self._emit_event(
                            "planner_tool_failed",
                            f"工具 {name} 参数被截断，强制结束工具调用阶段。",
                            iteration=iteration,
                            tool=name,
                            error_type="tool_args_truncated",
                            argument_chars=len(raw_args),
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                "Tool arguments were truncated. "
                                "Stop calling tools and return a concise final Markdown report "
                                "using the evidence already generated."
                            ),
                        })
                        continue
                    tool_result = {
                        "error": "invalid_tool_arguments",
                        "message": f"Tool arguments were not valid JSON: {exc}",
                        "repair_instruction": "Re-issue the same tool call with complete valid JSON arguments. Do not finalize.",
                    }
                    should_add_repair_prompt = True
                    await self._emit_event(
                        "planner_tool_failed",
                        f"工具 {name} 的参数不是有效 JSON，要求模型修复后重试。",
                        iteration=iteration,
                        tool=name,
                        error_type=type(exc).__name__,
                        error=str(exc),
                        argument_chars=len(tc.function.arguments or ""),
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })
                    continue

                if name == "execute_code":
                    tool_result = await self._call_execute_code(
                        args,
                        code_executor,
                        execution_results,
                    )
                elif name == "save_semantic_finding":
                    tool_result = await self._call_save_finding(args, finding_saver)
                else:
                    tool_result = await self._execute_tool(tc, skill_registry, preflight_markdown)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result,
                })
                await self._emit_event(
                    "planner_tool_completed",
                    f"工具 {name} 已返回。",
                    iteration=iteration,
                    tool=name,
                    result=self._summarize_tool_result(tool_result),
                )

            if should_add_repair_prompt:
                messages.append({
                    "role": "user",
                    "content": self._repair_prompt(latest_feedback, int(latest_feedback.get("repair_round", feedback_rounds) if latest_feedback else feedback_rounds + 1))
                    if latest_feedback
                    else "Repair the invalid tool call. Re-issue complete valid JSON arguments and continue the required workflow.",
                })
            if should_force_finalize:
                force_finalize = True
                diagnostic_state["force_finalize_count"] += 1
                await self._emit_event(
                    "planner_finalization_forced",
                    "执行或修复预算已用尽，下一次调用仅允许合成最终报告。",
                    iteration=iteration,
                    execution_count=len(execution_results),
                    feedback_rounds=feedback_rounds,
                )
                messages.append({
                    "role": "user",
                    "content": self._finalize_prompt(latest_feedback, execution_results),
                })

        await self._emit_final_payload_parsed(
            {
                "report_md": "",
                "title": question[:60],
                "summary": "Analysis did not complete within iteration limit",
                "selected_skills": [SkillRouter.route(question)],
                "caveats": ["LLM did not return an evidence-backed report within iteration limit"],
                "next_checks": [],
                "analysis_intent": analysis_intent,
                "candidate_angles": [],
                "chart_specs": [],
                "visual_plan": [],
                "feedback_evaluation": self._compact_feedback(latest_feedback),
            },
            parse_strategy="minimal_fallback",
            schema_valid=False,
            execution_results=execution_results,
        )
        return {
            "report_md": "",
            "title": question[:60],
            "summary": "Analysis did not complete within iteration limit",
            "selected_skills": [SkillRouter.route(question)],
            "caveats": ["LLM did not return an evidence-backed report within iteration limit"],
            "next_checks": [],
            "analysis_intent": analysis_intent,
            "candidate_angles": [],
            "chart_specs": [],
            "visual_plan": [],
            "feedback_evaluation": self._compact_feedback(latest_feedback),
        }

    @staticmethod
    def _should_retry_feedback(
        feedback: dict[str, Any] | None,
        feedback_rounds: int,
    ) -> bool:
        return bool(
            feedback
            and feedback.get("should_retry")
            and feedback_rounds < MAX_FEEDBACK_REPAIR_ROUNDS
        )

    def _check_report_sanity(
        self,
        normalized: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Check report_md content sanity and evidence integration."""
        report_md = normalized.get("report_md") or ""
        features = count_report_features(report_md)
        chart_specs = normalized.get("chart_specs") or []
        has_evidence = self._has_successful_evidence(execution_results)
        return check_report_sanity(
            report_md,
            chart_specs=chart_specs,
            chart_ref_count=features["chart_ref_count"],
            evidence_ref_count=features["evidence_ref_count"],
            has_evidence=has_evidence,
        )

    async def _emit_event(self, event_type: str, summary: str, **data: Any) -> None:
        event_sink = getattr(self, "event_sink", None)
        if event_sink is not None:
            await event_sink(event_type, summary, **data)

    async def _emit_final_payload_parsed(
        self,
        normalized: dict[str, Any],
        *,
        parse_strategy: str,
        schema_valid: bool,
        execution_results: list[dict[str, Any]],
    ) -> None:
        report_md = normalized.get("report_md") or ""
        features = count_report_features(report_md)
        quality_flags: list[str] = []
        if features["empty_or_tiny"]:
            quality_flags.append("report_too_short")
        if features["evidence_ref_count"] == 0:
            quality_flags.append("no_evidence_refs")
        chart_specs = normalized.get("chart_specs") or []
        if len(chart_specs) == 0:
            quality_flags.append("no_chart_specs")
        visual_plan = normalized.get("visual_plan") or []
        candidate_angles = normalized.get("candidate_angles") or []

        await self._emit_event(
            "planner_final_payload_parsed",
            "Final payload parsed and schema validated",
            parse_strategy=parse_strategy,
            schema_valid=schema_valid,
            report_md_chars=features["report_md_chars"],
            heading_count=features["heading_count"],
            table_row_count=features["table_row_count"],
            chart_ref_count=features["chart_ref_count"],
            evidence_ref_count=features["evidence_ref_count"],
            chart_specs_count=len(chart_specs),
            visual_plan_count=len(visual_plan),
            candidate_angles_count=len(candidate_angles),
            quality_flags=quality_flags,
        )

    async def _accept_payload(
        self,
        normalized: dict[str, Any],
        parse_strategy: str,
        schema_valid: bool,
        execution_results: list[dict[str, Any]],
        *,
        iteration: int,
        force_finalize: bool,
    ) -> dict[str, Any] | None:
        """Test report sanity, emit parsed event, and decide whether to accept.

        Returns the accepted payload, or None if rejected (caller must retry/fallback).
        """
        # Emit the parsed event first (always)
        await self._emit_final_payload_parsed(
            normalized,
            parse_strategy=parse_strategy,
            schema_valid=schema_valid,
            execution_results=execution_results,
        )

        if not schema_valid:
            return None

        # Sanity gate
        sanity = self._check_report_sanity(normalized, execution_results)
        if not sanity["report_sanity_passed"]:
            await self._emit_event(
                "planner_report_sanity_rejected",
                f"Report content sanity check failed: {sanity['failure_reason']}",
                failure_reason=sanity["failure_reason"],
                bad_markers=sanity["report_md_bad_markers"],
                code_marker_count=sanity["report_md_code_marker_count"],
                parse_strategy=parse_strategy,
                iteration=iteration,
                force_finalize=force_finalize,
            )
            return None

        return normalized

    @staticmethod
    def _summarize_tool_arguments(name: str, raw_args: str | None) -> dict[str, Any]:
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            return {"valid_json": False, "argument_chars": len(raw_args or "")}
        summary: dict[str, Any] = {
            "valid_json": True,
            "keys": sorted(args.keys()),
        }
        if name == "execute_code":
            summary.update({
                "step_name": args.get("step_name"),
                "step_description": args.get("step_description"),
                "angle_id": args.get("angle_id"),
                "code_chars": len(args.get("code") or ""),
            })
        else:
            summary["values"] = {
                key: value
                for key, value in args.items()
                if key not in {"api_key", "token", "secret", "password"}
            }
        return summary

    @staticmethod
    def _summarize_tool_result(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return {
                "keys": sorted(result.keys()),
                "error": result.get("error"),
                "returncode": result.get("returncode"),
                "table_count": len(result.get("tables") or []),
                "chart_count": len(result.get("charts") or []),
                "should_retry": result.get("should_retry"),
            }
        return {"type": type(result).__name__, "chars": len(str(result))}

    @staticmethod
    def _usage_summary(usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def _finalize_prompt(
        feedback: dict[str, Any] | None,
        execution_results: list[dict[str, Any]],
    ) -> str:
        successful = sum(
            1
            for result in execution_results
            if result.get("returncode") in (0, None) and result.get("status") != "failed"
        )
        feedback_summary = (feedback or {}).get("summary") or "No additional feedback."
        return (
            "## Finalize now\n\n"
            f"You have {successful} successful analysis step(s). The tool phase is complete or "
            "the execution/repair budget is exhausted. Do not call any more tools. Return ONLY "
            "one complete JSON object with "
            "title, summary, selected_skills, caveats, next_checks, report_md, analysis_intent, "
            "candidate_angles, chart_specs, visual_plan, and feedback_evaluation.\n\n"
            "Each visual_plan item must reference an existing Markdown section and choose a "
            "supported visual block type. Do not put calculated values in visual_plan; "
            "deterministic code binds values from report_md and evidence.\n\n"
            f"Use the evidence already collected. Remaining feedback:\n{feedback_summary}"
        )

    async def _call_execute_code(self, args: dict[str, Any], code_executor, execution_results: list[dict[str, Any]]) -> dict[str, Any]:
        if not code_executor:
            return {"error": "Code executor not available"}
        code = args.get("code", "")
        step_name = args.get("step_name", "")
        step_description = args.get("step_description", "")
        angle_id = args.get("angle_id", "")
        try:
            result = await code_executor(code, step_name, step_description, angle_id)
        except TypeError:
            result = await code_executor(code, step_name, step_description)
        normalized = self._normalize_execution_result(args, result)
        execution_results.append(normalized)
        return normalized

    @staticmethod
    async def _call_save_finding(args: dict[str, Any], finding_saver) -> dict[str, Any]:
        if not finding_saver:
            return {"error": "Finding saver not available"}
        return await finding_saver(
            args.get("metric_name", ""),
            args.get("definition", ""),
            args.get("aggregation", ""),
            args.get("grain", ""),
            args.get("source_column", ""),
            args.get("caveat", ""),
            args.get("source_dataset", ""),
        )

    async def _execute_tool(self, tool_call: Any, skill_registry: Any, preflight_markdown: str) -> str:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            return json.dumps({"error": "invalid_tool_arguments", "message": str(exc)}, ensure_ascii=False)
        if name == "list_skills":
            skills = skill_registry.list_skills() if skill_registry else []
            return json.dumps([{"id": s.id, "name": s.name, "trigger": s.trigger} for s in skills], ensure_ascii=False)
        if name == "load_skill":
            skill_id = args.get("skill_id", "")
            content = skill_registry.load_skill_content(skill_id) if skill_registry else None
            return content if content else f"Skill '{skill_id}' not found"
        if name == "read_preflight":
            return preflight_markdown
        return f"Unknown tool: {name}"

    def _available_tools(self, execution_count: int) -> list[dict[str, Any]]:
        tools = self._tool_definitions()
        limit = get_settings().planner_max_code_executions
        if execution_count >= limit:
            tools = [
                t for t in tools
                if t["function"]["name"] not in ("execute_code", "save_semantic_finding")
            ]
        if not getattr(self, "_require_evidence", True):
            tools = [t for t in tools if t["function"]["name"] not in ("execute_code", "save_semantic_finding")]
        return tools

    @classmethod
    def _tool_definitions(cls) -> list[dict[str, Any]]:
        return [
            cls._tool("list_skills", "List all available analysis skills", {}, []),
            cls._tool("read_preflight", "Read project preflight envelope", {}, []),
            cls._tool("load_skill", "Load full content of a specific skill", {"skill_id": {"type": "string"}}, ["skill_id"]),
            cls._tool(
                "execute_code",
                (
                    "Execute Python analysis code and return stdout, stderr, tables, and charts. "
                    "Use dataset_paths[0] directly. Save CSV/PNG/HTML evidence with relative "
                    "filenames in the current working directory; never write evidence to /tmp."
                ),
                {
                    "code": {"type": "string"},
                    "step_name": {"type": "string"},
                    "step_description": {"type": "string"},
                    "angle_id": {"type": "string"},
                    "repair_of": {
                        "type": "string",
                        "description": (
                            "When repairing a failed execution, copy the exact failed step_name here "
                            "so the trace and feedback evaluator can link the attempts."
                        ),
                    },
                },
                ["code", "step_name"],
            ),
            cls._tool(
                "save_semantic_finding",
                "Save a confirmed reusable metric definition to semantic layer",
                {
                    "metric_name": {"type": "string"},
                    "definition": {"type": "string"},
                    "aggregation": {"type": "string"},
                    "grain": {"type": "string"},
                    "source_column": {"type": "string"},
                    "caveat": {"type": "string"},
                    "source_dataset": {"type": "string"},
                },
                ["metric_name", "definition", "aggregation", "source_column"],
            ),

        ]

    @staticmethod
    def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    @staticmethod
    def _build_run_prompt(
        question: str,
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None,
        ad_hoc_context: str | None,
        analysis_intent: dict[str, Any] | None = None,
    ) -> str:
        parts = [
            "## Question",
            "",
            question,
            "",
            "## Datasets Available",
            "",
            Planner._format_profiles_for_prompt(profiles),
        ]
        parts.extend([
            "",
            format_analysis_dependency_status_for_prompt(),
        ])
        if analysis_intent:
            parts.extend(["", format_analysis_intent_for_prompt(analysis_intent)])
        if project_contexts:
            parts.extend(["", "## Project Context"])
            for ctx in project_contexts:
                if ctx.kind in ("source_routing", "semantic_layer", "business_context"):
                    parts.append(f"- {ctx.title} ({ctx.kind})")
        if ad_hoc_context:
            parts.extend(["", "## Additional Context", "", ad_hoc_context])
        parts.extend([
            "",
            "Follow the required workflow. Return the final JSON or Markdown report after completing analysis steps. The system will validate the report internally.",
            "Include analysis_intent in final JSON, copying the provided Pre-analysis Intent unless evidence clearly requires a correction.",
            "For each selected candidate angle, prefer an execute_code step whose step_description mentions the angle question or angle id.",
            "Candidate angle score fields must use the 0-1 scale. Example: 0.8, not 8.",
            "If the request already names exact metrics, dates, and outputs, keep candidate_angles empty and answer only that focused scope.",
            "Execution environment: selected dataset files are already available in the injected Python list `dataset_paths`; read them directly (for example, `pd.read_csv(dataset_paths[0])`). Never search the filesystem for datasets.",
            "Evidence output contract: save CSV, PNG, SVG, or HTML files with a relative filename in the current run directory. Do not write evidence files to /tmp because they will not be collected.",
            "Visual delivery contract: report, deep-dive, and dashboard requests require at least one decision-relevant chart. Save the chart in the current run directory and cite it in the core conclusion.",
            "Visual composition contract: include visual_plan in final JSON for report-like outputs. Each item uses {block_type, source_section, optional source_ref, title, intent, priority, options}. Choose only supported semantic block types from the visual template catalog. Reference headings and tables that actually exist in report_md. Do not copy numeric values into visual_plan; deterministic code extracts and validates them.",
            "Evidence integration contract: do not add a bottom-of-report list of referenced charts/tables. Evidence must be bound section-by-section through structured evidence_ids/source_refs, inline chart links like [业务标题](chart_name.html), compact tables, or hidden evidence anchors placed next to the relevant section.",
            "Performance contract: use vectorized groupby, agg, merge, and pivot operations. Do not loop over every source row while repeatedly filtering the full dataframe.",
            "Repair trace contract: when re-running a failed step, pass the exact previous step_name in execute_code.repair_of even if the new step_name changes.",
            "Column safety: use only exact column names shown in Available Data, or inspect df.columns before selecting columns. Do not use translated or business-label column names unless they are present verbatim.",
        ])
        return "\n".join(parts)

    FINALIZER_MIN_REPORT_CHARS = 300

    @staticmethod
    def _coerce_final_payload(
        content: str,
        *,
        question: str,
        analysis_intent: dict[str, Any] | None,
        force_finalize: bool,
        has_successful_evidence: bool = False,
        min_report_chars: int = 300,
    ) -> dict[str, Any] | None:
        payload = Planner._extract_json(content)
        if payload:
            if "report_md" not in payload:
                for alias in ("report", "markdown", "report_markdown"):
                    if isinstance(payload.get(alias), str):
                        payload["report_md"] = payload[alias]
                        break
            if "report_md" in payload:
                if force_finalize and has_successful_evidence:
                    if len((payload.get("report_md") or "").strip()) < min_report_chars:
                        return None
                return payload
            return None

        stripped = content.strip()
        if not force_finalize:
            return None

        if has_successful_evidence and len(stripped) < min_report_chars:
            return None

        recovered_report = Planner._extract_report_string(stripped)
        if recovered_report:
            stripped = recovered_report
        elif stripped.startswith("```") and stripped.endswith("```"):
            stripped = re.sub(r"^```(?:markdown|md)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)

        if has_successful_evidence and len(stripped.strip()) < min_report_chars:
            return None

        if not Planner._looks_like_markdown_report(stripped):
            if not force_finalize:
                return None
            stripped = stripped[:8000] if len(stripped) > 8000 else stripped
            if not stripped.startswith("#"):
                stripped = f"# Analysis Report\n\n{stripped}"

        if has_successful_evidence and len(stripped.strip()) < min_report_chars:
            return None

        heading = next(
            (
                line.lstrip("#").strip()
                for line in stripped.splitlines()
                if line.startswith("# ") and line.lstrip("#").strip()
            ),
            question[:60],
        )
        return {
            "title": heading,
            "summary": "",
            "selected_skills": [SkillRouter.route(question)],
            "caveats": [
                "The model returned final Markdown instead of the requested JSON wrapper."
            ],
            "next_checks": [],
            "report_md": stripped,
            "analysis_intent": analysis_intent or {},
            "candidate_angles": [],
            "chart_specs": [],
            "visual_plan": [],
            "feedback_evaluation": {},
        }

    @staticmethod
    def _extract_report_string(content: str) -> str | None:
        decoder = json.JSONDecoder()
        for key in ("report_md", "report", "markdown", "report_markdown"):
            match = re.search(rf'"{key}"\s*:\s*', content)
            if not match:
                continue
            try:
                value, _ = decoder.raw_decode(content[match.end():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _looks_like_markdown_report(content: str) -> bool:
        s = (content or "").strip()
        if len(s) < 200:
            return False
        heading_count = s.count("\n#") + (1 if s.startswith("#") else 0)
        has_table = "|" in s and "---" in s
        has_chart_link = ".html" in s
        has_business_terms = any(
            kw in s for kw in [
                "结论", "发现", "建议", "风险", "增长",
                "渠道", "品牌", "品类", "销售", "订单",
                "趋势", "占比", "同比", "环比",
                "conclusion", "finding", "recommendation",
            ]
        )
        return heading_count >= 1 or (has_business_terms and (has_table or has_chart_link))

    @staticmethod
    def _normalize_execution_result(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(result or {})
        normalized.setdefault("name", args.get("step_name", ""))
        normalized.setdefault("description", args.get("step_description", ""))
        if args.get("angle_id"):
            normalized.setdefault("angle_id", args.get("angle_id"))
        if args.get("repair_of"):
            normalized.setdefault("repair_of", args.get("repair_of"))
        normalized.setdefault("returncode", 0 if normalized.get("status") != "failed" else 1)
        normalized.setdefault("status", "completed" if normalized.get("returncode", 0) == 0 else "failed")
        normalized.setdefault("stdout", "")
        normalized.setdefault("stderr", "")
        normalized.setdefault("tables", [])
        normalized.setdefault("charts", [])
        return normalized

    @staticmethod
    def _context_budget_snapshot(
        messages: list[dict[str, Any]],
        execution_results: list[dict[str, Any]] | None = None,
        *,
        detached_finalizer_active: bool = False,
    ) -> dict[str, Any]:
        message_content_chars = 0
        tool_call_argument_chars = 0
        tool_result_chars = 0
        largest_items: list[dict[str, Any]] = []

        for index, message in enumerate(messages):
            role = str(message.get("role") or "")
            content = message.get("content") or ""
            content_chars = len(str(content))
            message_content_chars += content_chars

            item_chars = content_chars
            item_kind = f"message:{role}"

            if role == "tool":
                tool_result_chars += content_chars
                item_kind = "tool_result"

            tc_arg_chars = 0
            for tc in message.get("tool_calls") or []:
                function = tc.get("function") or {}
                args = function.get("arguments") or ""
                arg_chars = len(str(args))
                tool_call_argument_chars += arg_chars
                tc_arg_chars += arg_chars

            largest_items.append({
                "index": index,
                "role": role,
                "kind": item_kind,
                "content_chars": content_chars,
                "tool_call_argument_chars": tc_arg_chars,
                "total_chars": item_chars + tc_arg_chars,
            })

        estimated_context_chars = message_content_chars + tool_call_argument_chars

        execution_results = execution_results or []
        table_count = sum(len(r.get("tables") or []) for r in execution_results)
        chart_count = sum(len(r.get("charts") or []) for r in execution_results)

        largest_items = sorted(
            largest_items,
            key=lambda item: item["total_chars"],
            reverse=True,
        )[:_LLM_LARGEST_CONTEXT_ITEMS]

        settings = get_settings()
        action = "continue"
        if estimated_context_chars >= settings.planner_context_warn_chars:
            action = "warn"

        return {
            "message_count": len(messages),
            "message_content_chars": message_content_chars,
            "tool_call_argument_chars": tool_call_argument_chars,
            "tool_result_chars": tool_result_chars,
            "estimated_context_chars": estimated_context_chars,
            "largest_context_items": largest_items,
            "execution_count": len(execution_results),
            "table_count": table_count,
            "chart_count": chart_count,
            "detached_finalizer_active": detached_finalizer_active,
            "warn_threshold": settings.planner_context_warn_chars,
            "hard_threshold": settings.planner_context_hard_chars,
            "budget_action": action,
        }

    @staticmethod
    def _prompt_snapshot_for_event(messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a bounded, reviewable snapshot of the messages sent to the LLM."""
        total_messages = len(messages)
        if total_messages <= _LLM_PROMPT_SNAPSHOT_HEAD_MESSAGES + _LLM_PROMPT_SNAPSHOT_TAIL_MESSAGES:
            selected_indexes = list(range(total_messages))
            omitted_count = 0
        else:
            head_indexes = list(range(_LLM_PROMPT_SNAPSHOT_HEAD_MESSAGES))
            tail_indexes = list(range(total_messages - _LLM_PROMPT_SNAPSHOT_TAIL_MESSAGES, total_messages))
            selected_indexes = head_indexes + tail_indexes
            omitted_count = total_messages - len(selected_indexes)

        snapshot_messages: list[dict[str, Any]] = []
        for index in selected_indexes:
            message = messages[index]
            content = str(message.get("content") or "")
            tool_calls: list[dict[str, Any]] = []
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function") or {}
                arguments = Planner._readable_json_text(function.get("arguments") or "")
                tool_calls.append({
                    "name": function.get("name") or "",
                    "arguments_preview": safe_preview(
                        arguments,
                        head=_LLM_PROMPT_SNAPSHOT_HEAD_CHARS,
                        tail=_LLM_PROMPT_SNAPSHOT_TAIL_CHARS,
                    ),
                })
            snapshot_messages.append({
                "index": index,
                "role": str(message.get("role") or ""),
                "name": message.get("name"),
                "content_preview": safe_preview(
                    content,
                    head=_LLM_PROMPT_SNAPSHOT_HEAD_CHARS,
                    tail=_LLM_PROMPT_SNAPSHOT_TAIL_CHARS,
                ),
                "content_chars": len(content),
                "tool_call_count": len(tool_calls),
                "tool_calls": tool_calls,
            })

        total_chars = sum(len(str(message.get("content") or "")) for message in messages)
        return {
            "message_count": total_messages,
            "included_message_count": len(snapshot_messages),
            "omitted_message_count": omitted_count,
            "total_content_chars": total_chars,
            "head_chars": _LLM_PROMPT_SNAPSHOT_HEAD_CHARS,
            "tail_chars": _LLM_PROMPT_SNAPSHOT_TAIL_CHARS,
            "messages": snapshot_messages,
        }

    @staticmethod
    def _readable_json_text(value: Any) -> str:
        text = str(value or "")
        if not text.strip():
            return ""
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return text
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    @staticmethod
    def _should_detach_for_context_budget(
        budget: dict[str, Any],
        execution_results: list[dict[str, Any]],
        *,
        detached_finalizer_active: bool,
    ) -> bool:
        if detached_finalizer_active:
            return False
        if not execution_results:
            return False
        if budget.get("estimated_context_chars", 0) < get_settings().planner_context_warn_chars:
            return False
        has_evidence = any(
            (r.get("tables") or r.get("charts"))
            and r.get("status") != "failed"
            for r in execution_results
        )
        return has_evidence

    @staticmethod
    def _compact_profiles_for_finalizer(profiles: list[DatasetProfile]) -> list[dict[str, Any]]:
        settings = get_settings()
        compact = []
        for profile in profiles:
            columns = []
            for col in profile.columns[:settings.finalizer_profile_columns]:
                columns.append({
                    "name": col.name,
                    "dtype": col.dtype,
                })
            compact.append({
                "name": profile.filename,
                "rows": profile.row_count,
                "columns_count": profile.column_count,
                "columns": columns,
            })
        return compact

    def _compact_execution_result_for_finalizer(self, result: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        return {
            "name": result.get("name"),
            "description": result.get("description"),
            "status": result.get("status"),
            "returncode": result.get("returncode"),
            "stdout": (result.get("stdout_excerpt") or result.get("stdout") or "")[:settings.finalizer_stdout_chars_per_step],
            "tables": result.get("tables") or [],
            "charts": result.get("charts") or [],
        }

    def _build_finalizer_evidence_bundle(
        self,
        *,
        question: str,
        profiles: list[DatasetProfile],
        analysis_intent: dict[str, Any] | None,
        execution_results: list[dict[str, Any]],
        latest_feedback: dict[str, Any] | None,
        reason: str,
    ) -> dict[str, Any]:
        settings = get_settings()
        successful_steps = []
        failed_steps = []
        for result in execution_results:
            failed = (
                result.get("status") == "failed"
                or result.get("returncode") not in (0, None)
            )
            if failed:
                failed_steps.append({
                    "name": result.get("name"),
                    "returncode": result.get("returncode"),
                    "stderr": str(result.get("stderr") or "")[:settings.llm_stderr_char_limit],
                })
            else:
                successful_steps.append(
                    self._compact_execution_result_for_finalizer(result)
                )

        table_count = sum(len(r.get("tables") or []) for r in execution_results)
        chart_count = sum(len(r.get("charts") or []) for r in execution_results)

        tables_used = 0
        charts_used = 0
        omitted_tables = 0
        omitted_charts = 0
        for step in successful_steps:
            if tables_used >= settings.finalizer_max_tables:
                omitted_tables += len(step.get("tables") or [])
                step["tables"] = []
                step["tables_omitted"] = True
            else:
                remaining = settings.finalizer_max_tables - tables_used
                step_tables = step.get("tables") or []
                if len(step_tables) > remaining:
                    omitted_tables += len(step_tables) - remaining
                    step["tables"] = step_tables[:remaining]
                    step["tables_omitted"] = True
                tables_used += len(step["tables"])

            if charts_used >= settings.finalizer_max_charts:
                omitted_charts += len(step.get("charts") or [])
                step["charts"] = []
                step["charts_omitted"] = True
            else:
                remaining = settings.finalizer_max_charts - charts_used
                step_charts = step.get("charts") or []
                if len(step_charts) > remaining:
                    omitted_charts += len(step_charts) - remaining
                    step["charts"] = step_charts[:remaining]
                    step["charts_omitted"] = True
                charts_used += len(step["charts"])

        feedback_summary = {}
        if latest_feedback:
            feedback_summary = {
                "passed": latest_feedback.get("passed"),
                "hard_failure_count": latest_feedback.get("hard_failure_count", 0),
                "quality_miss_count": latest_feedback.get("quality_miss_count", 0),
                "quality_score": latest_feedback.get("quality_score"),
                "summary": latest_feedback.get("summary", ""),
            }

        expected_output = str((analysis_intent or {}).get("expected_output") or "")

        return {
            "reason": reason,
            "question": question,
            "analysis_intent": analysis_intent or {},
            "datasets": self._compact_profiles_for_finalizer(profiles),
            "successful_steps": successful_steps,
            "failed_steps": failed_steps[:settings.finalizer_max_failed_steps],
            "evidence_summary": {
                "table_count": table_count,
                "chart_count": chart_count,
                "successful_step_count": len(successful_steps),
                "failed_step_count": len(failed_steps),
                "omitted_tables": omitted_tables,
                "omitted_charts": omitted_charts,
            },
            "required_output_checklist": self._finalizer_checklist(expected_output),
            "feedback_summary": feedback_summary,
            "instructions": self._finalizer_instructions(),
        }

    @staticmethod
    def _finalizer_checklist(expected_output: str) -> list[str]:
        checklist = [
            "Answer the original question directly with a clear recommendation or conclusion.",
            "Cite specific evidence (tables, charts, numbers) to support each claim.",
        ]
        if expected_output in {"report", "deep_dive", "dashboard"}:
            checklist.append("Include at least one decision-relevant chart reference.")
        checklist.extend([
            "Mention key caveats and limitations.",
            "Suggest actionable next steps.",
        ])
        return checklist

    @staticmethod
    def _finalizer_instructions() -> list[str]:
        return [
            "Do not invent metrics, numbers, or column names not present in the evidence.",
            "Use exact chart file names (e.g. chart_trend.html) when citing evidence.",
            "Return ONLY one valid JSON object matching the output schema.",
            "Keep report_md focused and evidence-backed; avoid filler prose.",
            "Failed step partial outputs are not valid evidence — do not cite them.",
            "For chart_specs, include exact generated chart artifact names when charts exist.",
            "For visual_plan, reference section headings or table titles that actually exist in report_md.",
        ]

    def _build_detached_finalizer_messages(
        self,
        *,
        question: str,
        profiles: list[DatasetProfile],
        analysis_intent: dict[str, Any] | None,
        execution_results: list[dict[str, Any]],
        latest_feedback: dict[str, Any] | None,
        reason: str,
    ) -> list[dict[str, Any]]:
        bundle = self._build_finalizer_evidence_bundle(
            question=question,
            profiles=profiles,
            analysis_intent=analysis_intent,
            execution_results=execution_results,
            latest_feedback=latest_feedback,
            reason=reason,
        )

        system = (
            "You are a data analysis finalizer. "
            "Your task is to synthesize a decision-oriented report from compact evidence. "
            "Do not call tools. Use only the provided evidence bundle. "
            "Return ONLY one valid JSON object with the schema described below."
        )

        user = {
            "task": "Finalize the analysis report from compact evidence.",
            "output_schema": {
                "title": "string — concise report title",
                "summary": "string — 2-3 sentence executive summary",
                "selected_skills": "array of strings",
                "caveats": "array of strings",
                "next_checks": "array of strings",
                "report_md": "string — structured markdown report",
                "analysis_intent": "object",
                "candidate_angles": "array",
                "chart_specs": "array",
                "visual_plan": "array",
                "feedback_evaluation": "object",
            },
            "bundle": bundle,
            "rules": bundle.get("instructions", []),
        }

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ]

    @staticmethod
    def _has_successful_evidence(execution_results: list[dict[str, Any]]) -> bool:
        for result in execution_results:
            if result.get("returncode") in (0, None) and result.get("status") != "failed":
                if result.get("tables") or result.get("charts"):
                    return True
        return False

    def _evaluate_payload(
        self,
        question: str,
        payload: dict[str, Any],
        execution_results: list[dict[str, Any]],
        data_backed: bool,
    ) -> dict[str, Any]:
        return evaluate_attempt_feedback(
            question=question,
            report_md=payload.get("report_md", ""),
            execution_results=execution_results,
            selected_skills=payload.get("selected_skills", []),
            candidate_angles=payload.get("candidate_angles", []),
            chart_specs=payload.get("chart_specs", []),
            caveats=payload.get("caveats", []),
            data_backed=data_backed,
            analysis_intent=payload.get("analysis_intent"),
        )

    @staticmethod
    def _repair_prompt(feedback: dict[str, Any] | None, round_no: int) -> str:
        if not feedback:
            return "Repair the previous invalid output and continue the required workflow."
        mode = "repair hard failures" if feedback.get("hard_failure_count", 0) else "improve quality"
        return (
            f"## Feedback repair round {round_no}\n\n"
            f"Mode: {mode}\n"
            f"Quality score: {feedback.get('quality_score')}\n\n"
            f"{feedback.get('summary', '')}\n\n"
            "Continue the same analysis. When re-running a failed step, pass its exact step_name "
            "in execute_code.repair_of. Then return the final report."
        )

    @staticmethod
    def _must_execute_prompt(reason: str) -> str:
        return (
            "## Hard stop: evidence execution required\n\n"
            f"{reason}\n\n"
            "This is a data-backed request. Do not return final JSON yet. "
            "Call execute_code now, produce at least one CSV table or chart, then return the final report."
        )

    @staticmethod
    def _build_finalization_failed_payload(
        question: str,
        analysis_intent: dict[str, Any] | None,
        execution_results: list[dict[str, Any]],
        latest_feedback: dict[str, Any] | None,
        failure_reason: str,
    ) -> dict[str, Any]:
        """Return an explicit failure payload when finalization cannot produce a valid report."""
        return {
            "report_md": "",
            "title": question[:60],
            "summary": "Final report generation failed after evidence was produced.",
            "selected_skills": [SkillRouter.route(question)],
            "caveats": [
                "Final report synthesis failed; evidence artifacts were generated but not safely integrated."
            ],
            "next_checks": [],
            "analysis_intent": analysis_intent or {},
            "candidate_angles": [],
            "chart_specs": [],
            "visual_plan": [],
            "feedback_evaluation": Planner._compact_feedback_static(latest_feedback),
            "_finalization_failed": True,
            "_finalization_failure_reason": failure_reason,
        }

    @staticmethod
    def _compact_feedback_static(feedback: dict[str, Any] | None) -> dict[str, Any]:
        if not feedback:
            return {}
        return {
            "passed": feedback.get("passed"),
            "should_retry": feedback.get("should_retry"),
            "hard_failure_count": feedback.get("hard_failure_count", 0),
            "quality_miss_count": feedback.get("quality_miss_count", 0),
            "quality_score": feedback.get("quality_score"),
            "repair_limit_reached": feedback.get("repair_limit_reached", False),
        }

    @staticmethod
    def _compact_feedback(feedback: dict[str, Any] | None) -> dict[str, Any]:
        return Planner._compact_feedback_static(feedback)

    @staticmethod
    def _normalize_report_payload(payload: dict[str, Any], question: str, analysis_intent: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "report_md": payload.get("report_md", ""),
            "title": payload.get("title", question[:60]),
            "summary": payload.get("summary", ""),
            "selected_skills": payload.get("selected_skills", []) or [SkillRouter.route(question)],
            "caveats": payload.get("caveats", []),
            "next_checks": payload.get("next_checks", []),
            "analysis_intent": payload.get("analysis_intent") or analysis_intent or {},
            "candidate_angles": Planner._normalize_candidate_angles(
                payload.get("candidate_angles", [])
            ),
            "chart_specs": payload.get("chart_specs", []),
            "visual_plan": Planner._normalize_visual_plan(payload.get("visual_plan", [])),
            "feedback_evaluation": payload.get("feedback_evaluation", {}),
        }

    @staticmethod
    def _validate_payload_schema(normalized: dict[str, Any], question: str) -> dict[str, Any] | None:
        try:
            PlannerFinalPayload.model_validate(normalized)
            return normalized
        except Exception:
            return None

    @staticmethod
    def _schema_repair_prompt(normalized: dict[str, Any], question: str) -> str:
        missing: list[str] = []
        for key in ("title", "report_md"):
            if not normalized.get(key):
                missing.append(key)
        if missing:
            return (
                "The previous response is missing required fields: "
                f"{', '.join(missing)}. Your final JSON MUST include "
                "a 'title' (string) and 'report_md' (string containing "
                "the markdown report). Re-send the complete JSON."
            )
        return (
            "The previous response JSON did not pass schema validation. "
            "Ensure all required fields are present: title (string), "
            "report_md (string), candidate_angles (array), chart_specs (array), "
            "visual_plan (array). Re-send the complete JSON."
        )

    @staticmethod
    def _normalize_candidate_angles(value: Any) -> list[dict[str, Any]]:
        score_fields = (
            "impact_score",
            "confidence_score",
            "actionability_score",
            "novelty_score",
            "relevance_score",
            "data_sufficiency_score",
        )
        normalized: list[dict[str, Any]] = []
        for raw_angle in value if isinstance(value, list) else []:
            if not isinstance(raw_angle, dict):
                continue
            angle = dict(raw_angle)
            question = next(
                (
                    angle.get(key)
                    for key in ("question", "angle", "title", "name")
                    if angle.get(key)
                ),
                None,
            )
            if not question:
                continue
            angle["question"] = str(question)
            for field in ("dimensions", "measures"):
                field_value = angle.get(field, [])
                if isinstance(field_value, str):
                    angle[field] = [field_value]
                elif not isinstance(field_value, list):
                    angle[field] = []
            for field in score_fields:
                try:
                    score = float(angle.get(field, 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                if 1.0 < score <= 10.0:
                    score /= 10.0
                angle[field] = min(1.0, max(0.0, score))
            normalized.append(angle)
        return normalized

    @staticmethod
    def _normalize_visual_plan(value: Any) -> list[dict[str, Any]]:
        supported = {
            "executive_storyboard", "adaptive_story",
            "kpi_grid", "metric_change", "trend_panel", "composition_panel",
            "leaderboard_pair", "delta_bridge", "decision_matrix", "comparison_grid",
            "stage_timeline", "next_action_list", "risk_panel", "data_quality_panel",
            "forecast_band", "insight_banner", "page_summary",
        }
        result: list[dict[str, Any]] = []
        for index, raw in enumerate(value if isinstance(value, list) else []):
            if not isinstance(raw, dict):
                continue
            block_type = str(raw.get("block_type") or raw.get("type") or "").strip()
            source_section = str(raw.get("source_section") or raw.get("section") or "").strip()
            if block_type not in supported or not source_section:
                continue
            result.append({
                "id": str(raw.get("id") or f"visual_plan_{index + 1}"),
                "block_type": block_type,
                "source_section": source_section,
                "source_ref": str(raw.get("source_ref") or "").strip() or None,
                "title": str(raw.get("title") or "").strip() or None,
                "intent": str(raw.get("intent") or raw.get("purpose") or "").strip() or None,
                "priority": str(raw.get("priority") or "primary"),
                "options": raw.get("options") if isinstance(raw.get("options"), dict) else {},
            })
        return result[:24]

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any] | None:
        if not content:
            return None

        decoder = json.JSONDecoder()
        candidates: list[str] = []
        found: list[dict[str, Any]] = []

        raw = content.strip()
        candidates.append(raw)

        for m in re.finditer(
            r"```(?:json|JSON)?\s*(.*?)\s*```",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        ):
            fenced = m.group(1).strip()
            if fenced:
                candidates.append(fenced)

        for candidate in candidates:
            search_end = min(len(candidate), 120_000)
            for start in [m.start() for m in re.finditer(r"\{", candidate[:search_end])]:
                try:
                    obj, _end = decoder.raw_decode(candidate[start:])
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    if (
                        "report_md" in obj
                        or "report" in obj
                        or "markdown" in obj
                        or "report_markdown" in obj
                    ):
                        return obj
                    found.append(obj)

        if found:
            return found[0]

        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    async def _repair_final_payload_format(
        self,
        invalid_content: str,
        *,
        question: str,
        analysis_intent: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        await self._emit_event(
            "planner_final_output_format_repair_started",
            "模型返回格式无效，启动格式修复器。",
            content_chars=len(invalid_content),
            content_preview=invalid_content[:500],
        )

        content_for_repair = invalid_content[:60_000] if len(invalid_content) > 60_000 else invalid_content

        system = (
            "You are a strict JSON formatter. "
            "The input below is a malformed final answer from a data analysis agent. "
            "Convert it into ONE valid JSON object only. "
            "Do not add new analysis. Do not change facts, numbers, chart filenames, or table names. "
            "Preserve the report content as much as possible. "
            "Escape all newlines and quotes correctly inside report_md. "
            "Return only JSON, no markdown fence, no explanation."
        )

        schema_desc = (
            "Required JSON schema:\n"
            '{\n'
            '  "title": string,\n'
            '  "summary": string,\n'
            '  "selected_skills": array,\n'
            '  "caveats": array,\n'
            '  "next_checks": array,\n'
            '  "report_md": string,\n'
            '  "analysis_intent": object,\n'
            '  "candidate_angles": array,\n'
            '  "chart_specs": array,\n'
            '  "visual_plan": array,\n'
            '  "feedback_evaluation": object\n'
            '}'
        )

        user = (
            "## Malformed output to repair\n\n"
            f"{content_for_repair}\n\n"
            f"{schema_desc}\n\n"
            f"Original question (for context): {question[:200]}"
        )

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }

        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass

        try:
            response = await self.client.chat.completions.create(
                **self._completion_kwargs(**kwargs)
            )
        except Exception:
            try:
                kwargs.pop("response_format", None)
                response = await self.client.chat.completions.create(
                    **self._completion_kwargs(**kwargs)
                )
            except Exception as exc:
                await self._emit_event(
                    "planner_final_output_format_repair_failed",
                    f"格式修复器调用失败：{exc}",
                    error=str(exc),
                )
                return None

        repaired_text = (response.choices[0].message.content or "").strip()
        repaired = self._extract_json(repaired_text)

        if repaired and isinstance(repaired, dict) and repaired.get("report_md"):
            await self._emit_event(
                "planner_final_output_format_repair_completed",
                "格式修复完成。",
                repaired_report_chars=len(repaired.get("report_md", "")),
            )
            return repaired

        await self._emit_event(
            "planner_final_output_format_repair_failed",
            "格式修复器返回内容无法解析。",
            repaired_content_preview=repaired_text[:500],
        )
        return None

    async def generate_plan(
        self,
        question: str,
        skill_content: str,
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None = None,
        ad_hoc_context: str | None = None,
        auxiliary_skills: dict[str, str] | None = None,
        preflight_markdown: str | None = None,
    ) -> dict[str, Any]:
        user_message = self._build_plan_prompt(
            question, skill_content, profiles, project_contexts, ad_hoc_context,
            auxiliary_skills, preflight_markdown,
        )
        response = await self.client.chat.completions.create(
            **self._completion_kwargs(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": _RESOLVED_PLANNER_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=resolve_temperature(self.config.temperature),
                response_format={"type": "json_object"},
            )
        )
        return self._parse_json(response.choices[0].message.content or "{}")

    async def synthesize_report(
        self,
        question: str,
        skill_content: str,
        plan_title: str,
        plan_summary: str,
        step_results: list[dict[str, Any]],
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None = None,
        ad_hoc_context: str | None = None,
        template_content: str | None = None,
    ) -> str:
        user_message = self._build_report_prompt(
            question, skill_content, plan_title, plan_summary,
            step_results, profiles, project_contexts, ad_hoc_context,
            template_content,
        )
        response = await self.client.chat.completions.create(
            **self._completion_kwargs(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": _RESOLVED_PLANNER_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=resolve_temperature(self.config.temperature, default=0.3),
            )
        )
        return response.choices[0].message.content or ""

    def _build_plan_prompt(
        self,
        question: str,
        skill_content: str,
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None,
        ad_hoc_context: str | None,
        auxiliary_skills: dict[str, str] | None = None,
        preflight_markdown: str | None = None,
    ) -> str:
        intent = infer_analysis_intent(question, profiles, project_contexts, ad_hoc_context)
        parts = ["## Task", "", "Generate a focused analysis plan. Output ONLY valid JSON.", "", f"**Question:** {question}"]
        parts.extend(["", format_analysis_intent_for_prompt(intent)])
        if preflight_markdown:
            parts.extend(["", "## Project Preflight", "", preflight_markdown])
        if project_contexts:
            parts.extend(["", "## Project Context"])
            for ctx in project_contexts:
                parts.extend([f"### {ctx.title} ({ctx.kind})", ctx.body, ""])
        if ad_hoc_context:
            parts.extend(["", "## Additional Context", "", ad_hoc_context])
        if auxiliary_skills:
            for aux_name, aux_content in auxiliary_skills.items():
                parts.extend(["", f"## Auxiliary Skill: {aux_name}", "", aux_content])
        parts.extend([
            "", "## Analysis Skill", "", skill_content,
            "", "## Available Data", "", self._format_profiles_for_prompt(profiles),
            "", "Return ONLY the JSON plan, nothing else.",
        ])
        return "\n".join(parts)

    def _build_report_prompt(
        self,
        question: str,
        skill_content: str,
        plan_title: str,
        plan_summary: str,
        step_results: list[dict[str, Any]],
        profiles: list[DatasetProfile],
        project_contexts: list[ProjectContext] | None,
        ad_hoc_context: str | None,
        template_content: str | None = None,
    ) -> str:
        parts = [
            "## Task", "", "Synthesize evidence into a decision-oriented Markdown report.", "",
            f"**Original Question:** {question}",
            f"**Analysis Title:** {plan_title}",
            f"**Summary:** {plan_summary}",
            "", "## Analysis Evidence", "",
        ]
        for i, result in enumerate(step_results):
            parts.extend([
                f"### Step {i + 1}: {result.get('name', 'Unknown')}",
                f"**Description:** {result.get('description', '')}",
                f"**Status:** {result.get('status', 'unknown')}",
            ])
            if result.get("stdout"):
                parts.extend(["", "**Output:**", "", "```", str(result["stdout"])[:3000], "```"])
            if result.get("stderr"):
                parts.extend(["", "**Errors:**", "", "```", str(result["stderr"])[:1000], "```"])
            if result.get("tables"):
                parts.append("**Generated Tables:")
                for table in result["tables"]:
                    parts.append(f"- `{table.get('name', 'table')}` ({table.get('rows', '?')} rows)")
            if result.get("charts"):
                parts.append("**Generated Charts:**")
                for chart in result["charts"]:
                    parts.append(f"- `{chart.get('name', 'chart')}` ({chart.get('type', 'unknown')})")
            parts.append("")
        if template_content:
            parts.extend(["", "## Report Structure (REQUIRED)", "", template_content])
        parts.extend(["", "Return ONLY the Markdown report, nothing else."])
        return "\n".join(parts)

    @staticmethod
    def _format_profiles_for_prompt(profiles: list[DatasetProfile]) -> str:
        if not profiles:
            return "No dataset profiles available."
        lines: list[str] = []
        for profile in profiles:
            lines.append(f"### {profile.filename}")
            lines.append(f"- Rows: {profile.row_count}")
            lines.append(f"- Columns: {profile.column_count}")
            for col in profile.columns:
                extras = []
                if col.mean_value is not None:
                    extras.append(f"mean={col.mean_value:.2f}")
                if col.unique_count <= 20:
                    samples = ", ".join(str(v) for v in col.sample_values[:5] if v)
                    if samples:
                        extras.append(f"samples=[{samples}]")
                extra_str = f" ({', '.join(extras)})" if extras else ""
                lines.append(
                    f"  - {col.name}: {col.dtype}, {col.non_null_count} non-null "
                    f"({col.null_pct:.1f}% null), {col.unique_count} unique{extra_str}"
                )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "Failed to parse plan JSON", "raw": raw[:500]}
