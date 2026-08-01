"""Registry of in-flight runs used for cancellation."""
from __future__ import annotations

import asyncio
from typing import Any

_registry: dict[str, dict[str, Any]] = {}


def register_run(run_id: str, task: asyncio.Task, orchestrator: Any) -> None:
    _registry[str(run_id)] = {"task": task, "orchestrator": orchestrator}


def unregister_run(run_id: str) -> None:
    _registry.pop(str(run_id), None)


def cancel_run(run_id: str) -> bool:
    """Request cancellation of a registered run task."""
    entry = _registry.get(str(run_id))
    if entry is None:
        return False
    task = entry["task"]
    if not task.done():
        task.cancel()
    return True


def active_run_ids() -> list[str]:
    return sorted(_registry)


def clear_registry() -> None:
    """Clear all registered runs (test/diagnostic helper)."""
    _registry.clear()
