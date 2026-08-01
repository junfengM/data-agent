"""Factory for the save_finding closure used to persist discovered metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.memory.store import MemoryStore
from app.models.schemas import RunResponse, ToolCall
from app.tools.path_safety import PathSafetyError, resolve_project_yaml_path
from app.tools.preflight import select_active_layer


def create_save_finding(
    store: MemoryStore,
    workspace_dir: Path,
    project_id: str | None,
    run: RunResponse,
):
    """Create a save_finding closure that persists discovered metrics.

    Returns an async function that writes a metric to the project-scoped
    semantic layer YAML file.
    """

    async def save_finding(
        metric_name: str,
        definition: str,
        aggregation: str,
        grain: str,
        source_column: str,
        caveat: str,
        source_dataset: str = "",
    ) -> dict:
        """Persist a discovered metric to the PROJECT-SCOPED semantic layer.

        Captures full provenance: source column, dataset, aggregation, grain,
        caveat, timestamp, and run_id.
        """
        if not project_id:
            return {
                "saved": False,
                "error": "Cannot save semantic finding: no project_id in request"
            }

        project_layers = store.list_semantic_layers(project_id)
        active_layer = select_active_layer(project_layers) if project_layers else None

        try:
            if active_layer:
                layer_path = resolve_project_yaml_path(
                    workspace_dir=workspace_dir,
                    project_id=project_id,
                    requested_path=active_layer["path"],
                )
            else:
                layer_path = resolve_project_yaml_path(
                    workspace_dir=workspace_dir,
                    project_id=project_id,
                    requested_path="semantic-layer.yaml",
                )
        except PathSafetyError as exc:
            return {"saved": False, "error": str(exc)}

        layer_path.parent.mkdir(parents=True, exist_ok=True)

        if not layer_path.exists():
            layer_path.write_text("metrics: []\ndimensions: []\ncaveats: []\n", encoding="utf-8")
            existing_layers = store.list_semantic_layers(project_id)
            if not any(l.get("path") == str(layer_path) for l in existing_layers):
                created = store.create_semantic_layer({
                    "project_id": project_id,
                    "name": "Discovered Metrics",
                    "path": str(layer_path),
                    "is_active": True,
                })
                store.promote_active_layer(project_id, created["id"])

        data = yaml.safe_load(layer_path.read_text(encoding="utf-8")) or {}
        metrics = data.setdefault("metrics", [])

        for m in metrics:
            if m.get("name") == metric_name:
                return {"saved": False, "reason": "duplicate", "metric": metric_name}

        entry = {
            "name": metric_name,
            "description": definition,
            "formula": definition,
            "aggregation": aggregation,
            "grain": grain,
            "sources": [{"dataset": source_dataset, "column": source_column}],
            "caveats": [caveat] if caveat else [],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run.id,
            "owner": "model_suggested",
        }
        metrics.append(entry)

        layer_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        run.tool_calls.append(ToolCall(
            name="save_semantic_finding",
            input_summary=f"{metric_name} = {definition}",
            output_summary=f"Saved metric '{metric_name}' to project semantic layer",
            status="completed",
        ))
        return {"saved": True, "metric": metric_name, "path": "<project_semantic_layer>"}

    return save_finding
