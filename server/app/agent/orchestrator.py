"""Agent orchestrator — wires skill routing, LLM planning, tool execution, and artifact generation."""
import asyncio
import logging
from pathlib import Path
import time
from typing import Any, Awaitable, Callable

from app.agent.dataset_profiling import build_profile_artifacts, profile_datasets
from app.agent.planner import Planner
from app.agent.planner_bridge import create_execute_step
from app.agent.run_context import contexts_to_markdown, load_project_context
from app.agent.run_lifecycle import (
    build_run_log_markdown,
    build_workflow_template,
    complete_step,
    create_event_emitter,
)
from app.agent.semantic_finding_service import create_save_finding
from app.agent.skills import SkillRegistry
from app.agent.templates import TemplateRegistry
from app.agent.visual_adaptation import learn_visual_recipes
from app.core.model_config import ModelConfigRegistry
from app.core.settings import Settings
from app.memory.store import MemoryStore
from app.models.schemas import (
    AnalysisRequest,
    Artifact,
    ArtifactType,
    CandidateAngle,
    RunEventType,
    RunResponse,
    ToolCall,
)
from app.tools.markdown import profiles_to_markdown
from app.tools.redaction import redact_local_paths
from app.tools.preflight import (
    build_preflight_envelope, derive_semantic_layer,
    load_semantic_layer, load_source_category_config, preflight_to_markdown,
    select_active_layer,
)
from app.agent.artifact_manifest import (
    build_report_blocks, draft_fallback_report,
)
from app.agent.semantic_findings import enforce_angle_boundaries
from app.agent.visual_report_assembly import assemble_visual_report
from app.agent.run_validation import run_and_apply_validation
from app.agent.run_artifacts import (
    write_markdown_artifact,
    write_visual_report_artifact,
    write_html_artifact,
    write_notebook_artifact,
    write_web_report_artifact,
)

RunEventSink = Callable[[dict[str, Any]], Awaitable[None]]

_MODEL_FAILURE_HINTS = (
    "api key",
    "unauthorized",
    "authentication",
    "401",
    "403",
    "missing model",
    "no model",
    "connection",
    "timeout",
    "rate limit",
    "429",
    "server error",
    "service unavailable",
    "503",
)


def _looks_like_model_failure(reason: str) -> bool:
    """Classify planner errors that should fail the run instead of falling back."""
    lowered = reason.lower()
    return any(hint in lowered for hint in _MODEL_FAILURE_HINTS)


def _create_plan_only_executor(run: RunResponse, emit: Any, step_results_list: list[dict]):
    """Return an execute_step stub that records intent without running code.

    The planner still generates code and calls execute_step, but the stub
    captures the intent without executing anything on the host.
    """

    async def execute_step(code: str, step_name: str, step_desc: str) -> dict:
        await emit(
            RunEventType.CODE_GENERATED,
            f"已生成分析代码：{step_name}（plan_only 模式，不实际执行）。",
            step_name=step_name,
            step_description=step_desc,
            code=code,
        )
        await emit(
            "code_execution_skipped",
            f"plan_only 模式，跳过代码执行：{step_name}。",
            step_name=step_name,
        )

        run.tool_calls.append(
            ToolCall(
                name="analysis_step_plan_only",
                input_summary=f"{step_name}: {step_desc[:80]}" if step_desc else step_name,
                output_summary="plan_only: execution disabled, intent recorded.",
                status="completed",
            )
        )

        step_results_list.append({
            "name": step_name,
            "description": step_desc,
            "code": code,
            "status": "skipped",
            "stdout": "",
            "stderr": "",
            "tables": [],
            "charts": [],
        })

        return {
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "status": "skipped",
            "tables": [],
            "charts": [],
        }

    return execute_step


class AgentOrchestrator:
    def __init__(
        self,
        skills_dir: Path,
        workspace_dir: Path,
        config_dir: Path,
        store: MemoryStore,
        generated_code_execution: str = "disabled",
        templates_dir: Path | None = None,
        emit_debug_structured_report: bool = False,
    ) -> None:
        self.skill_registry = SkillRegistry(skills_dir)
        self.workspace_dir = workspace_dir
        self.config_dir = config_dir
        self.store = store
        self.generated_code_execution = generated_code_execution
        self.templates_dir = templates_dir
        self.emit_debug_structured_report = emit_debug_structured_report

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgentOrchestrator":
        return cls(
            skills_dir=settings.resolved_skills_dir,
            workspace_dir=settings.resolved_workspace_dir,
            config_dir=settings.resolved_config_dir,
            store=MemoryStore(settings.resolved_sqlite_path),
            generated_code_execution=settings.generated_code_execution,
            templates_dir=settings.resolved_templates_dir,
            emit_debug_structured_report=settings.emit_debug_structured_report,
        )

    async def run(self, request: AnalysisRequest, event_sink: RunEventSink | None = None) -> RunResponse:
        run_started_at = time.perf_counter()

        model_config = self._resolve_model_config(request.model_config_id)

        # 1. Create run and workflow
        run = RunResponse(
            status="running",
            skill_id=request.skill_id or "auto",
            question=request.question,
            project_id=request.project_id,
            run_mode=request.run_mode,
        )
        run.workflow_steps = build_workflow_template("auto")
        run_dir = self.workspace_dir / "artifacts" / run.id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.store.record_run(run)

        emit = create_event_emitter(self.store, run, run_started_at, event_sink)

        await emit(
            RunEventType.RUN_STARTED,
            "\u5df2\u521b\u5efa\u8fd0\u884c\u4efb\u52a1\uff0c\u5f00\u59cb\u8bfb\u53d6\u9879\u76ee\u3001\u4e0a\u4e0b\u6587\u548c\u6570\u636e\u8f93\u5165\u3002",
            run_id=run.id,
            project_id=request.project_id,
            dataset_ids=request.dataset_ids,
            model_config_id=model_config.id if model_config else request.model_config_id,
            model=model_config.model if model_config else None,
            model_provider=model_config.provider if model_config else None,
            run_mode=request.run_mode,
        )

        try:
            await self._run_pipeline(request, run, run_dir, emit, model_config)
        except asyncio.CancelledError:
            run.status = "cancelled"
            self._persist_run_status(run)
            raise
        except Exception as exc:
            run.status = "failed"
            run.tool_calls.append(
                ToolCall(
                    name="run_error",
                    input_summary=request.question[:80],
                    output_summary=f"Run failed: {exc}",
                    status="failed",
                )
            )
            try:
                await emit(
                    "run_failed",
                    f"\u8fd0\u884c\u5f02\u5e38\u7ec8\u6b62\uff1a{exc}",
                    error=str(exc),
                )
            except Exception:
                pass
            self._persist_run_status(run)
            raise
        self._persist_run_status(run)
        return run

    def _persist_run_status(self, run: RunResponse) -> None:
        """Persist the final run status even when a later step raised."""
        try:
            self.store.record_run(run)
        except Exception:
            logging.getLogger(__name__).exception("failed to persist run final status")

    async def _run_pipeline(
        self,
        request: AnalysisRequest,
        run: RunResponse,
        run_dir: Path,
        emit: Any,
        model_config: Any,
    ) -> RunResponse:
        # 2. Load project context
        project, project_contexts = load_project_context(self.store, request.project_id)
        await emit(
            RunEventType.CONTEXT_LOADED,
            f"\u5df2\u8bfb\u53d6\u9879\u76ee\u4e0a\u4e0b\u6587\uff1a{len(project_contexts)} \u6761\u3002",
            project_name=project.name if project else None,
            context_count=len(project_contexts),
            has_run_context=bool(request.context),
        )

        # 3. Profile datasets
        await emit(
            RunEventType.DATASET_PROFILE_STARTED,
            f"\u5f00\u59cb\u8bfb\u53d6\u5e76\u753b\u50cf {len(request.dataset_ids)} \u4e2a\u6570\u636e\u96c6\u3002",
            dataset_ids=request.dataset_ids,
        )
        profiles = profile_datasets(self.store, request.dataset_ids)
        profile_markdown = profiles_to_markdown(profiles)
        await emit(
            RunEventType.DATASET_PROFILE_COMPLETED,
            f"\u6570\u636e\u753b\u50cf\u5b8c\u6210\uff1a{len(profiles)} \u4e2a\u6570\u636e\u96c6\u53ef\u7528\u4e8e\u5206\u6790\u3002",
            profiles=[profile.model_dump(mode="json") for profile in profiles],
        )

        if profiles:
            build_profile_artifacts(profiles, run)
            complete_step(run, "analysis", "\u6570\u636e\u96c6\u753b\u50cf\u5b8c\u6210\u3002")

        # 4. Build preflight envelope
        # Load project semantic layer first. No-project runs use only auto-derived
        # semantic layer from uploaded data; global config is reserved for project runs.
        project_layers = self.store.list_semantic_layers(request.project_id)
        active_layer = select_active_layer(project_layers) if project_layers else None
        selected_layer_id: str | None = None
        if active_layer:
            semantic_layer_path = Path(active_layer["path"])
            selected_layer_id = active_layer["id"]
        elif request.project_id:
            # No project-local layer exists; derive from profiles or leave empty.
            # config/semantic-layer.yaml is a schema template, not a runtime fallback.
            semantic_layer_path = None
        else:
            semantic_layer_path = None  # ephemeral: no global config access

        semantic_layer = load_semantic_layer(semantic_layer_path)

        # Auto-derive temporary semantic layer if YAML has no metrics (MVP single-file scenario)
        if not semantic_layer.metrics and profiles:
            semantic_layer = derive_semantic_layer(profiles)

        source_routing = self.store.get_source_routing(request.project_id)
        onboarding_progress = self.store.get_onboarding_progress(request.project_id)
        source_category_config = load_source_category_config(self.config_dir / "source-category-config.yaml")
        preflight = build_preflight_envelope(
            project=project,
            project_contexts=project_contexts,
            semantic_layer=semantic_layer,
            profiles=profiles,
            source_routing=source_routing,
            onboarding_progress=onboarding_progress,
            source_category_config=source_category_config,
            project_layers=project_layers,
        )
        preflight_markdown = preflight_to_markdown(preflight)
        layer_info = selected_layer_id or ("auto-derived" if profiles else "none")
        run.tool_calls.append(
            ToolCall(
                name="project_preflight",
                input_summary=project.name if project else "No project",
                output_summary=f"Preflight: {len(preflight.context_gaps)} gap(s), semantic layer: {layer_info}",
                status="completed",
            )
        )
        await emit(
            RunEventType.PREFLIGHT_COMPLETED,
            f"\u8fd0\u884c\u524d\u68c0\u67e5\u5b8c\u6210\uff1a\u53d1\u73b0 {len(preflight.context_gaps)} \u4e2a\u4e0a\u4e0b\u6587\u7f3a\u53e3\uff0c\u8bed\u4e49\u5c42\uff1a{layer_info}\u3002",
            context_gap_count=len(preflight.context_gaps),
            semantic_layer=layer_info,
        )

        # 4.5 preflight_only early exit — no LLM, no code, no report
        if request.run_mode == "preflight_only":
            complete_step(run, "diagnosis", "preflight_only 模式跳过诊断。")
            complete_step(run, "report", "preflight_only 模式跳过报告生成。")
            run.status = "completed"
            run.tool_calls.append(
                ToolCall(
                    name="run_mode_preflight_only",
                    input_summary="preflight_only mode selected",
                    output_summary="Skipped LLM, code execution, and report generation.",
                    status="completed",
                )
            )
            await emit(
                "run_completed",
                "运行前检查完成（preflight_only 模式），已跳过分析、执行和报告阶段。",
                status=run.status,
                run_mode="preflight_only",
            )
            run_log_data = redact_local_paths({
                "run_mode": "preflight_only",
                "preflight": {
                    "context_gap_count": len(preflight.context_gaps),
                    "semantic_layer": layer_info,
                },
                "tool_calls": [call.model_dump(mode="json") for call in run.tool_calls],
                "workflow_steps": [step.model_dump(mode="json") for step in run.workflow_steps],
                "caveats": [],
                "next_checks": [],
            })
            run.artifacts.append(
                Artifact(
                    type=ArtifactType.run_log,
                    title="工作流日志",
                    content=build_run_log_markdown(run, run_log_data),
                    data=run_log_data,
                )
            )
            return run

        # 5. Single LLM conversation: route → execute → synthesize
        step_results: list[dict] = []
        _step_results: list[dict] = []
        plan_caveats: list[str] = []
        next_checks: list[str] = []
        skill_content = ""
        selected_skill_ids: list[str] = []
        candidate_angles: list[CandidateAngle] = []
        visual_plan: list[dict[str, Any]] = []

        try:
            if model_config is None:
                raise RuntimeError("No model configuration available")
            planner = Planner(model_config)
            planner.set_event_sink(emit)

            index_path = self.skill_registry.skills_dir / "index.md"
            with open(index_path, "r", encoding="utf-8") as f:
                planner.set_index_content(f.read())

            context_markdown = contexts_to_markdown(project, project_contexts, request.context)

            # Define code executor closure (or stub for plan_only)
            dataset_paths = self._dataset_paths(request.dataset_ids)
            if request.run_mode == "plan_only":
                execute_step = _create_plan_only_executor(run, emit, _step_results)
            else:
                execute_step = create_execute_step(
                    run_dir, dataset_paths, self.generated_code_execution, run, emit, _step_results,
                )
            save_finding = create_save_finding(
                self.store, self.workspace_dir, request.project_id, run,
            )

            await emit(
                RunEventType.PLANNING_STARTED,
                "\u5f00\u59cb\u8c03\u7528\u6a21\u578b\u5236\u5b9a\u5206\u6790\u65b9\u6848\u5e76\u6267\u884c\u6570\u636e\u5206\u6790\u6b65\u9aa4\u3002",
                model_config_id=model_config.id,
                model=model_config.model,
                provider=model_config.provider,
            )
            result = await planner.run_analysis(
                question=request.question,
                preflight_markdown=preflight_markdown,
                profiles=profiles,
                project_contexts=project_contexts,
                ad_hoc_context=request.context,
                skill_registry=self.skill_registry,
                code_executor=execute_step,
                finding_saver=save_finding,
                require_evidence=request.run_mode != "plan_only",
            )

            selected_skill_ids = result.get("selected_skills") or []
            if not selected_skill_ids:
                selected_skill_ids = [request.skill_id or "auto"]
            plan_title = result.get("title") or request.question[:60]
            plan_summary = result.get("summary") or ""
            report_md = result.get("report_md") or ""
            plan_caveats = result.get("caveats") or []
            next_checks = result.get("next_checks") or []
            candidate_angles = []
            for angle_data in result.get("candidate_angles", []):
                try:
                    candidate_angles.append(CandidateAngle(**angle_data))
                except Exception as exc:
                    await emit(
                        RunEventType.CANDIDATE_ANGLE_INVALID,
                        "\u5019\u9009\u5206\u6790\u89d2\u5ea6\u5143\u6570\u636e\u65e0\u6548\uff0c\u5df2\u8df3\u8fc7\u8be5\u89d2\u5ea6\u5e76\u4fdd\u7559\u62a5\u544a\u6b63\u6587\u3002",
                        error=str(exc),
                        angle=angle_data,
                    )
            chart_specs = result.get("chart_specs", [])
            visual_plan = result.get("visual_plan", [])
            step_results = _step_results

            # Pre-artifact gate: reject finalization failures before writing polished artifacts
            if result.get("_finalization_failed"):
                failure_reason = result.get("_finalization_failure_reason", "unknown")
                run.status = "failed"
                await emit(
                    "planner_finalization_failed",
                    f"Final report generation failed: {failure_reason}. Skipping artifact generation.",
                    failure_reason=failure_reason,
                    execution_count=len(step_results),
                )
                run_log_data = redact_local_paths({
                    "run_mode": request.run_mode,
                    "plan": {"title": plan_title, "summary": plan_summary, "skills": selected_skill_ids},
                    "workflow_steps": [step.model_dump(mode="json") for step in run.workflow_steps],
                    "tool_calls": [call.model_dump(mode="json") for call in run.tool_calls],
                    "step_results": step_results,
                    "caveats": [f"Finalization failed: {failure_reason}"],
                    "next_checks": [],
                    "finalization_failed": True,
                    "finalization_failure_reason": failure_reason,
                })
                run.artifacts.append(
                    Artifact(
                        type=ArtifactType.run_log,
                        title="工作流日志",
                        content=build_run_log_markdown(run, run_log_data),
                        data=run_log_data,
                    )
                )
                return run

            if not report_md.strip():
                raise RuntimeError(plan_summary or "LLM planner returned an empty report")

            # Enforce candidate angle boundaries for open-ended analysis.
            if candidate_angles:
                report_md, candidate_angles = enforce_angle_boundaries(
                    report_md=report_md,
                    candidate_angles=candidate_angles,
                    min_selected=2,
                    max_selected=3,
                )

            run.skill_id = selected_skill_ids[0]
            run.tool_calls.append(
                ToolCall(
                    name="llm_planner",
                    input_summary=f"Model={model_config.id}; question={request.question[:80]}",
                    output_summary=f"LLM selected skills: {', '.join(selected_skill_ids)}",
                    status="completed",
                )
            )

            if selected_skill_ids:
                skill_content = self.skill_registry.load_skill_content(selected_skill_ids[0]) or ""

            report_template: str | None = None
            if self.templates_dir and self.templates_dir.exists():
                template_registry = TemplateRegistry(self.templates_dir)
                report_template = template_registry.template_for_skill(selected_skill_ids[0])

            complete_step(run, "analysis", f"LLM \u8ba1\u5212: {plan_summary}")
            complete_step(run, "diagnosis", "LLM \u81ea\u4e3b\u6267\u884c\u5206\u6790\u6b65\u9aa4\u3002")
            complete_step(run, "report", "\u62a5\u544a\u5408\u6210\u5b8c\u6210\u3002")
            await emit(
                RunEventType.DIAGNOSIS_COMPLETED,
                "\u6a21\u578b\u5df2\u5b8c\u6210\u8bca\u65ad\u63a8\u7406\u6458\u8981\uff0c\u5f00\u59cb\u6574\u7406\u6700\u7ec8\u62a5\u544a\u3002",
                selected_skills=selected_skill_ids,
            )

        except Exception as planner_error:
            reason = str(planner_error)
            is_no_model = "no model" in reason.lower()
            from app.agent.skills import SkillRouter
            skill_id = selected_skill_ids[0] if selected_skill_ids else SkillRouter.route(request.question)
            run.skill_id = skill_id
            run.tool_calls.append(
                ToolCall(
                    name="llm_planner",
                    input_summary=f"Planning with {model_config.id}" if model_config else "no model",
                    output_summary=f"Planner failed: {planner_error}",
                    status="failed",
                )
            )
            await emit(
                RunEventType.PLANNING_FAILED,
                f"\u6a21\u578b\u89c4\u5212\u5931\u8d25\uff0c\u8f6c\u5165 fallback \u62a5\u544a\uff1a{planner_error}",
                error=str(planner_error),
            )
            if (is_no_model or _looks_like_model_failure(reason)) and not _step_results:
                run.status = "failed"
                run.artifacts.append(
                    Artifact(
                        type=ArtifactType.run_log,
                        title="\u8fd0\u884c\u5931\u8d25",
                        content=(
                            "\u6a21\u578b\u8c03\u7528\u5931\u8d25\u4e14\u6ca1\u6709\u53ef\u7528\u7684\u5206\u6790\u8bc1\u636e\uff0c\u5df2\u505c\u6b62\u4ea7\u7269\u751f\u6210\u3002\n\n"
                            "\u8bf7\u68c0\u67e5\u6a21\u578b\u914d\u7f6e\u4e0e API Key \u540e\u91cd\u8bd5\u3002\n\n"
                            f"\u9519\u8bef\u4fe1\u606f\uff1a{planner_error}"
                        ),
                        data={"reason": reason, "failed_stage": "planner"},
                    )
                )
                return run
            context_markdown = contexts_to_markdown(project, project_contexts, request.context)
            report_md = draft_fallback_report(
                request, skill_id, profiles, profile_markdown,
                project, context_markdown, _step_results, {},
            )
            plan_caveats = [f"LLM planner unavailable: {planner_error}"]
            next_checks = []
            plan_title = f"Fallback: {request.question[:60]}"
            plan_summary = f"Planner failed: {planner_error}"
            step_results = _step_results
            chart_specs = []
            visual_plan = []

        # 9. Write report artifacts
        await emit(
            RunEventType.REPORT_GENERATION_STARTED,
            "\u5f00\u59cb\u5199\u5165 Markdown\u3001HTML\u3001\u7ed3\u6784\u5316\u62a5\u544a\u548c notebook \u4ea7\u7269\u3002",
        )
        _, md_artifact = write_markdown_artifact(
            artifacts_dir=self.workspace_dir / "artifacts",
            run_id=run.id,
            report_md=report_md,
            workspace_root=self.workspace_dir,
        )
        run.artifacts.append(md_artifact)

        # Legacy debug artifact \u2014 only emitted when explicitly enabled.
        if self.emit_debug_structured_report:
            report_blocks = build_report_blocks(
                title=plan_title,
                report_md=report_md,
                step_results=step_results,
                plan_caveats=plan_caveats,
                profiles=profiles,
                project_contexts=project_contexts,
            )
            run.artifacts.append(
                Artifact(
                    type=ArtifactType.structured_report,
                    title="Block Report (Debug)",
                    content=report_md,
                    data={"blocks": [b.model_dump() for b in report_blocks]},
                )
            )

        # New: visual_report with manifest + snapshot separation
        manifest, snapshot = assemble_visual_report(
            title=plan_title,
            report_md=report_md,
            step_results=step_results,
            profiles=profiles,
            project_contexts=project_contexts,
            candidate_angles=candidate_angles,
            chart_specs=chart_specs,
            plan_caveats=plan_caveats,
            semantic_layer=semantic_layer,
            semantic_layer_path=str(semantic_layer_path) if semantic_layer_path else None,
            visual_plan=visual_plan,
            workspace_dir=self.workspace_dir,
            project_id=request.project_id,
        )

        learned_visual_recipes = learn_visual_recipes(
            self.workspace_dir,
            request.project_id,
            list(getattr(manifest, "visual_iteration", []) or []),
        )
        visual_artifact = write_visual_report_artifact(manifest, snapshot, report_md, workspace_root=self.workspace_dir)
        run.artifacts.append(visual_artifact)

        # Web Report artifact (post-Markdown delivery rendering).
        # Failure here must NOT affect run status — wrapped in try/except.
        try:
            web_artifact = write_web_report_artifact(
                run_id=run.id,
                report_md=report_md,
                manifest=manifest.model_dump(mode="json") if hasattr(manifest, "model_dump") else None,
                snapshot=snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else None,
                project_name=project.name if project else None,
                artifacts_dir=self.workspace_dir / "artifacts" / run.id,
                workspace_root=self.workspace_dir,
            )
            if web_artifact:
                run.artifacts.append(web_artifact)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("delivery web report failed", exc_info=True)

        _, html_artifact = write_html_artifact(
            artifacts_dir=self.workspace_dir / "artifacts",
            run_id=run.id,
            report_md=report_md,
            workspace_root=self.workspace_dir,
        )
        run.artifacts.append(html_artifact)

        _, notebook_artifact = write_notebook_artifact(
            artifacts_dir=self.workspace_dir / "artifacts",
            run_id=run.id,
            question=request.question,
            dataset_paths=self._dataset_paths(request.dataset_ids),
            profiles=profiles,
            workspace_root=self.workspace_dir,
        )
        run.artifacts.append(notebook_artifact)
        await emit(
            RunEventType.REPORT_GENERATED,
            "\u62a5\u544a\u4ea7\u7269\u5df2\u751f\u6210\u3002",
            artifact_count=len(run.artifacts),
            report_preview=report_md[:1200],
        )

        # 9.5 Run validation gates
        await emit(
            RunEventType.VALIDATION_STARTED,
            "\u5f00\u59cb\u6267\u884c\u62a5\u544a\u4e0e\u4ea7\u7269\u9a8c\u8bc1\u3002",
        )
        validation_passed, fail_count, warn_count, validation_results = run_and_apply_validation(
            run=run,
            manifest=manifest,
            step_results=step_results,
            report_md=report_md,
            plan_caveats=plan_caveats,
            profiles=profiles,
            semantic_layer=semantic_layer,
            preflight=preflight,
            project_contexts=project_contexts,
            run_mode=request.run_mode,
            chart_specs=chart_specs,
            artifacts_dir=run_dir,
        )

        validation_summary = f"{sum(1 for v in validation_results if v.passed)}/{len(validation_results)} gates passed"
        if fail_count > 0:
            tool_status = "failed"
        elif warn_count > 0:
            tool_status = "warning"
        else:
            tool_status = "completed"
        run.tool_calls.append(
            ToolCall(
                name="validation_gate",
                input_summary="Run validation gates",
                output_summary=validation_summary,
                status=tool_status,
            )
        )

        await emit(
            RunEventType.VALIDATION_COMPLETED,
            f"\u9a8c\u8bc1\u5b8c\u6210\uff1a{validation_summary}\u3002",
            validation_passed=validation_passed,
            fail_count=fail_count,
            warning_count=warn_count,
        )

        if fail_count > 0:
            run.status = "failed"
        elif warn_count > 0:
            run.status = "completed_with_warnings"
        else:
            run.status = "completed"

        run_log_data = redact_local_paths({
            "run_mode": request.run_mode,
            "plan": {
                "title": plan_title,
                "summary": plan_summary,
                "skills": selected_skill_ids,
            },
            "workflow_steps": [step.model_dump(mode="json") for step in run.workflow_steps],
            "tool_calls": [call.model_dump(mode="json") for call in run.tool_calls],
            "step_results": step_results,
            "validation_results": [v.__dict__ for v in validation_results],
            "validation_passed": validation_passed,
            "active_semantic_layer": self._active_semantic_layer_snapshot(request.project_id),
            "selected_skills": selected_skill_ids,
            "candidate_angles": [angle.model_dump(mode="json") for angle in candidate_angles],
            "chart_specs": chart_specs,
            "visual_plan": visual_plan,
            "visual_coverage": list(getattr(manifest, "visual_coverage", []) or []),
            "learned_visual_recipes": learned_visual_recipes,
            "caveats": plan_caveats,
            "next_checks": next_checks,
        })
        run.artifacts.append(
            Artifact(
                type=ArtifactType.run_log,
                title="\u5de5\u4f5c\u6d41\u65e5\u5fd7",
                content=build_run_log_markdown(run, run_log_data),
                data=run_log_data,
            )
        )

        return run

    def _active_semantic_layer_snapshot(self, project_id: str | None) -> dict[str, Any] | None:
        if not project_id:
            return None
        project_layers = self.store.list_semantic_layers(project_id)
        active_layer = select_active_layer(project_layers) if project_layers else None
        if not active_layer:
            return None
        layer_path = Path(active_layer["path"]) if active_layer.get("path") else None
        return {
            "id": active_layer.get("id"),
            "name": active_layer.get("name"),
            "path": str(layer_path) if layer_path else None,
        }

    def _resolve_model_config(self, model_id: str | None):
        registry = ModelConfigRegistry(self.config_dir / "models.yaml")
        return registry.get_model(model_id)

    def _dataset_paths(self, dataset_ids: list[str]) -> list[Path]:
        paths: list[Path] = []
        for dataset_id in dataset_ids:
            dataset = self.store.get_dataset(dataset_id)
            if dataset is not None:
                paths.append(dataset.path)
        return paths
