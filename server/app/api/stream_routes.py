import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import AgentOrchestrator
from app.agent.run_registry import register_run, unregister_run
from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import AnalysisRequest

router = APIRouter(tags=["runs"])
STREAM_HEARTBEAT_SECONDS = 15


def _validate_run_request(request: AnalysisRequest, store: MemoryStore) -> None:
    if request.project_id and request.dataset_ids:
        for dataset_id in request.dataset_ids:
            dataset = store.get_dataset(dataset_id)
            if dataset is None:
                raise HTTPException(status_code=400, detail=f"Dataset not found: {dataset_id}")
            if dataset.project_id and dataset.project_id != request.project_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Dataset {dataset_id} belongs to project "
                        f"{dataset.project_id}, not {request.project_id}"
                    ),
                )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.post("/runs/stream")
async def stream_run(request: AnalysisRequest) -> StreamingResponse:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    _validate_run_request(request, store)

    async def event_generator():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        orchestrator = AgentOrchestrator.from_settings(settings)

        async def emit(event: dict[str, Any]) -> None:
            await queue.put({"kind": "event", **event})

        async def run_task() -> None:
            try:
                result = await orchestrator.run(request, event_sink=emit)
                store.record_run(result)
                await queue.put({"kind": "result", "run": result.model_dump(mode="json")})
            except Exception as exc:
                await queue.put({"kind": "error", "summary": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_task())
        registered_run_id: str | None = None
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=STREAM_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield _sse({
                        "kind": "event",
                        "type": "heartbeat",
                        "summary": "任务仍在执行，连接保持中。",
                        "data": {"interval_seconds": STREAM_HEARTBEAT_SECONDS},
                    })
                    continue
                if item is None:
                    break
                if registered_run_id is None:
                    run_id = item.get("run_id")
                    if run_id:
                        registered_run_id = str(run_id)
                        register_run(registered_run_id, task, orchestrator)
                yield _sse(item)
        finally:
            if registered_run_id:
                unregister_run(registered_run_id)
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run_route(run_id: str) -> dict:
    """Cancel an in-flight streamed run by cancelling its asyncio task."""
    from app.agent.run_registry import cancel_run

    if not cancel_run(run_id):
        raise HTTPException(status_code=404, detail="No active run with this id")
    return {"run_id": run_id, "status": "cancelled"}
