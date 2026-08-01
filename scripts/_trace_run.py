#!/usr/bin/env python3
"""Run one local analysis with detailed execution tracing.

This script does not change agent behavior. It wraps the OpenAI-compatible client
used by Planner, captures orchestrator events, and writes an execution_trace.json
file that can be shared for performance and failure analysis.

Examples:
  ./scripts/trace-run \
    --question "分析一下本周销售变化" \
    --project-id <project_id> \
    --dataset-id <dataset_id>

  ./scripts/trace-run --question "What stands out?" --dataset-ids id1,id2 --include-code
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

import anyio  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def safe_len(value: Any) -> int | None:
    try:
        return len(value)  # type: ignore[arg-type]
    except Exception:
        return None


class ExecutionTrace:
    """In-memory trace recorder with conservative redaction and truncation."""

    SECRET_KEYS = ("api_key", "apikey", "token", "secret", "password", "authorization")

    def __init__(self, *, include_code: bool = False, include_llm_content: bool = False, max_string_chars: int = 1200) -> None:
        self.include_code = include_code
        self.include_llm_content = include_llm_content
        self.max_string_chars = max_string_chars
        self.started_monotonic = time.perf_counter()
        self.payload: dict[str, Any] = {
            "schema_version": 1,
            "started_at": utc_now(),
            "ended_at": None,
            "duration_ms": None,
            "run_id": None,
            "request": {},
            "environment": {
                "project_root": str(PROJECT_ROOT),
                "python": sys.version.split()[0],
            },
            "events": [],
            "llm_calls": [],
            "errors": [],
            "final": {},
        }

    def set_request(self, request: Any, settings: Any, model_config: Any | None = None) -> None:
        self.payload["request"] = {
            "question": getattr(request, "question", ""),
            "project_id": getattr(request, "project_id", None),
            "dataset_ids": list(getattr(request, "dataset_ids", []) or []),
            "model_config_id": getattr(request, "model_config_id", None),
            "skill_id": getattr(request, "skill_id", None),
            "has_context": bool(getattr(request, "context", None)),
        }
        self.payload["environment"].update({
            "config_dir": str(settings.resolved_config_dir),
            "workspace_dir": str(settings.resolved_workspace_dir),
            "skills_dir": str(settings.resolved_skills_dir),
            "sqlite_path": str(settings.resolved_sqlite_path),
            "generated_code_execution": settings.generated_code_execution,
        })
        if model_config is not None:
            self.payload["model"] = {
                "id": getattr(model_config, "id", None),
                "provider": getattr(model_config, "provider", None),
                "model": getattr(model_config, "model", None),
                "base_url": getattr(model_config, "base_url", None),
                "temperature": getattr(model_config, "temperature", None),
                "max_tokens": getattr(model_config, "max_tokens", None),
            }

    async def event_sink(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data") or {}
        if event_type == "run_started" and data.get("run_id"):
            self.payload["run_id"] = data.get("run_id")
        self.payload["events"].append({
            "at": utc_now(),
            "elapsed_ms": elapsed_ms(self.started_monotonic),
            "type": event_type,
            "summary": event.get("summary"),
            "data": self.sanitize(data),
        })

    def record_llm_call(self, call: dict[str, Any]) -> None:
        self.payload["llm_calls"].append(call)

    def record_error(self, stage: str, exc: BaseException, *, extra: dict[str, Any] | None = None) -> None:
        self.payload["errors"].append({
            "at": utc_now(),
            "elapsed_ms": elapsed_ms(self.started_monotonic),
            "stage": stage,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:],
            "extra": self.sanitize(extra or {}),
        })

    def finalize(self, run: Any | None = None) -> None:
        self.payload["ended_at"] = utc_now()
        self.payload["duration_ms"] = elapsed_ms(self.started_monotonic)
        if run is not None:
            self.payload["run_id"] = getattr(run, "id", self.payload.get("run_id"))
            validation_results = getattr(run, "validation_results", []) or []
            self.payload["final"] = {
                "status": getattr(run, "status", None),
                "skill_id": getattr(run, "skill_id", None),
                "artifact_count": len(getattr(run, "artifacts", []) or []),
                "tool_call_count": len(getattr(run, "tool_calls", []) or []),
                "tool_calls": [self.sanitize(_model_dump(tc)) for tc in (getattr(run, "tool_calls", []) or [])],
                "validation_passed": getattr(run, "validation_passed", None),
                "validation_fail_count": sum(1 for v in validation_results if getattr(v, "severity", None) == "fail" and not getattr(v, "passed", False)),
                "validation_warning_count": sum(1 for v in validation_results if getattr(v, "severity", None) == "warning" and not getattr(v, "passed", False)),
                "artifacts": [
                    {
                        "id": getattr(a, "id", None),
                        "type": str(getattr(a, "type", "")),
                        "title": getattr(a, "title", None),
                        "path": str(getattr(a, "path", "")) if getattr(a, "path", None) else None,
                        "content_chars": len(getattr(a, "content", "") or ""),
                        "data_keys": sorted((getattr(a, "data", None) or {}).keys()),
                    }
                    for a in (getattr(run, "artifacts", []) or [])
                ],
            }
        self.payload["summary"] = self._summary()

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def sanitize(self, value: Any, *, key: str = "") -> Any:
        key_lower = key.lower()
        if any(secret in key_lower for secret in self.SECRET_KEYS):
            return "[REDACTED]"
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k == "code" and not self.include_code:
                    out[k] = {"omitted": True, "chars": len(v or "")}
                else:
                    out[k] = self.sanitize(v, key=str(k))
            return out
        if isinstance(value, list):
            return [self.sanitize(v, key=key) for v in value[:200]]
        if isinstance(value, tuple):
            return [self.sanitize(v, key=key) for v in value[:200]]
        if isinstance(value, str):
            limit = self.max_string_chars
            if len(value) > limit:
                return value[:limit] + f"… [truncated {len(value) - limit} chars]"
            return value
        return value

    def _summary(self) -> dict[str, Any]:
        llm_calls = self.payload.get("llm_calls", [])
        usage = [c.get("usage") or {} for c in llm_calls]
        events = self.payload.get("events", [])
        return {
            "event_count": len(events),
            "llm_call_count": len(llm_calls),
            "llm_total_duration_ms": sum(int(c.get("duration_ms") or 0) for c in llm_calls),
            "prompt_tokens": sum(int(u.get("prompt_tokens") or 0) for u in usage),
            "completion_tokens": sum(int(u.get("completion_tokens") or 0) for u in usage),
            "total_tokens": sum(int(u.get("total_tokens") or 0) for u in usage),
            "requested_tool_calls": _count_requested_tool_calls(llm_calls),
            "error_count": len(self.payload.get("errors", [])),
            "event_types": _histogram(e.get("type") for e in events),
        }


def _model_dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    return dict(obj) if isinstance(obj, dict) else {"repr": repr(obj)}


def _histogram(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value)
        out[key] = out.get(key, 0) + 1
    return out


def _count_requested_tool_calls(llm_calls: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in llm_calls:
        for name in call.get("requested_tool_calls") or []:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _tool_names_from_definitions(tools: Any) -> list[str]:
    names: list[str] = []
    for tool in tools or []:
        try:
            names.append(tool.get("function", {}).get("name") or tool.get("name") or "unknown")
        except Exception:
            names.append("unknown")
    return names


def _message_char_count(messages: Any, *, include_content: bool) -> tuple[int, list[dict[str, Any]] | None]:
    total = 0
    previews: list[dict[str, Any]] = []
    for i, message in enumerate(messages or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "unknown")
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        content_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str) if content is not None else ""
        total += len(content_text)
        if include_content:
            previews.append({"index": i, "role": role, "content_preview": content_text[:2000], "content_chars": len(content_text)})
    return total, previews if include_content else None


def _summarize_tool_call_args(name: str, raw_args: str | None) -> dict[str, Any]:
    raw_args = raw_args or "{}"
    try:
        args = json.loads(raw_args)
    except Exception:
        return {"raw_chars": len(raw_args), "parse_error": True}
    if name == "execute_code":
        return {
            "step_name": args.get("step_name"),
            "step_description": args.get("step_description"),
            "angle_id": args.get("angle_id"),
            "code_chars": len(args.get("code") or ""),
        }
    if name == "evaluate_attempt":
        return {
            "report_md_chars": len(args.get("report_md") or ""),
            "selected_skills": args.get("selected_skills", []),
            "candidate_angle_count": len(args.get("candidate_angles") or []),
            "chart_spec_count": len(args.get("chart_specs") or []),
            "caveat_count": len(args.get("caveats") or []),
        }
    if name == "save_semantic_finding":
        return {
            "metric_name": args.get("metric_name"),
            "aggregation": args.get("aggregation"),
            "grain": args.get("grain"),
            "source_column": args.get("source_column"),
            "source_dataset": args.get("source_dataset"),
        }
    return args


def patch_openai_client(trace: ExecutionTrace):
    """Patch app.agent.planner.AsyncOpenAI and return a restore callback."""
    import app.agent.planner as planner_mod

    original_async_openai = planner_mod.AsyncOpenAI

    class TracingCompletions:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        async def create(self, **kwargs: Any) -> Any:
            iteration = len(trace.payload["llm_calls"]) + 1
            started = time.perf_counter()
            messages = kwargs.get("messages") or []
            approx_prompt_chars, message_previews = _message_char_count(
                messages,
                include_content=trace.include_llm_content,
            )
            call_record: dict[str, Any] = {
                "iteration": iteration,
                "at": utc_now(),
                "model": kwargs.get("model"),
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
                "tool_choice": kwargs.get("tool_choice"),
                "available_tools": _tool_names_from_definitions(kwargs.get("tools")),
                "message_count": len(messages),
                "approx_prompt_chars": approx_prompt_chars,
            }
            if message_previews is not None:
                call_record["messages"] = message_previews
            try:
                response = await self._inner.create(**kwargs)
            except Exception as exc:
                call_record.update({
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                })
                trace.record_llm_call(call_record)
                trace.record_error("llm_call", exc, extra={"iteration": iteration})
                raise

            duration = int((time.perf_counter() - started) * 1000)
            choice = response.choices[0] if getattr(response, "choices", None) else None
            msg = choice.message if choice is not None else None
            requested_tool_calls: list[str] = []
            requested_tool_call_args: list[dict[str, Any]] = []
            for tc in getattr(msg, "tool_calls", None) or []:
                name = tc.function.name
                requested_tool_calls.append(name)
                requested_tool_call_args.append({
                    "name": name,
                    "arguments": _summarize_tool_call_args(name, tc.function.arguments),
                    "arguments_chars": len(tc.function.arguments or ""),
                })
            content = getattr(msg, "content", None) if msg is not None else None
            call_record.update({
                "duration_ms": duration,
                "status": "completed",
                "finish_reason": getattr(choice, "finish_reason", None) if choice is not None else None,
                "response_id": getattr(response, "id", None),
                "content_chars": len(content or ""),
                "content_preview": (content or "")[:2000] if trace.include_llm_content else None,
                "requested_tool_calls": requested_tool_calls,
                "requested_tool_call_args": requested_tool_call_args,
                "usage": _usage_to_dict(getattr(response, "usage", None)),
            })
            trace.record_llm_call(call_record)
            return response

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    class TracingChat:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self.completions = TracingCompletions(inner.completions)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    class TracingAsyncOpenAI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._inner = original_async_openai(*args, **kwargs)
            self.chat = TracingChat(self._inner.chat)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    planner_mod.AsyncOpenAI = TracingAsyncOpenAI

    def restore() -> None:
        planner_mod.AsyncOpenAI = original_async_openai

    return restore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Data Agent analysis and write execution_trace.json")
    parser.add_argument("--question", required=True, help="Analysis question to run")
    parser.add_argument("--project-id", default=None, help="Existing project id")
    parser.add_argument("--dataset-id", action="append", default=[], help="Dataset id; repeat for multiple datasets")
    parser.add_argument("--dataset-ids", default="", help="Comma-separated dataset ids")
    parser.add_argument("--model-config-id", default=None, help="Optional model config id")
    parser.add_argument("--skill-id", default=None, help="Optional initial skill id")
    parser.add_argument("--context", default=None, help="Run-specific context")
    parser.add_argument("--output", default=None, help="Output trace path. Defaults to workspace/artifacts/<run_id>/execution_trace.json")
    parser.add_argument("--include-code", action="store_true", help="Include generated code in trace events. Default only records code length.")
    parser.add_argument("--include-llm-content", action="store_true", help="Include LLM message/content previews. May contain sensitive data.")
    parser.add_argument("--max-string-chars", type=int, default=1200, help="Max string chars per field before truncation")
    return parser.parse_args()


def _dataset_ids_from_args(args: argparse.Namespace) -> list[str]:
    ids = list(args.dataset_id or [])
    if args.dataset_ids:
        ids.extend([part.strip() for part in args.dataset_ids.split(",") if part.strip()])
    return ids


def _default_trace_path(settings: Any, run_id: str | None) -> Path:
    if run_id:
        return settings.resolved_workspace_dir / "artifacts" / run_id / "execution_trace.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return settings.resolved_workspace_dir / "artifacts" / "trace-errors" / f"execution_trace_{stamp}.json"


async def run_with_trace(args: argparse.Namespace) -> int:
    from app.agent.orchestrator import AgentOrchestrator
    from app.core.model_config import ModelConfigRegistry
    from app.core.settings import get_settings
    from app.memory.store import MemoryStore
    from app.models.schemas import AnalysisRequest

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    request = AnalysisRequest(
        question=args.question,
        project_id=args.project_id,
        dataset_ids=_dataset_ids_from_args(args),
        model_config_id=args.model_config_id,
        skill_id=args.skill_id,
        context=args.context,
    )

    model_config = None
    try:
        model_config = ModelConfigRegistry(settings.resolved_config_dir / "models.yaml").get_model(request.model_config_id)
    except Exception:
        # Orchestrator will surface the same failure; trace records it there.
        model_config = None

    trace = ExecutionTrace(
        include_code=args.include_code,
        include_llm_content=args.include_llm_content,
        max_string_chars=args.max_string_chars,
    )
    trace.set_request(request, settings, model_config)

    restore_openai = patch_openai_client(trace)
    run = None
    exit_code = 0
    try:
        orchestrator = AgentOrchestrator.from_settings(settings)
        run = await orchestrator.run(request, event_sink=trace.event_sink)
        store.record_run(run)
    except Exception as exc:
        trace.record_error("orchestrator.run", exc)
        exit_code = 1
    finally:
        restore_openai()
        trace.finalize(run)
        trace_path = Path(args.output) if args.output else _default_trace_path(settings, trace.payload.get("run_id"))
        trace.write(trace_path)
        print(f"execution_trace: {trace_path}")
        if run is not None:
            print(f"run_id: {run.id}")
            print(f"status: {run.status}")
        if trace.payload.get("errors"):
            print(f"errors: {len(trace.payload['errors'])}")
            for err in trace.payload["errors"][-3:]:
                print(f"  - {err.get('stage')}: {err.get('error_type')}: {err.get('message')}")
    return exit_code


if __name__ == "__main__":
    sys.exit(anyio.run(run_with_trace, parse_args()))
