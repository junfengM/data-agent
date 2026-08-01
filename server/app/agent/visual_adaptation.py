"""Project-scoped declarative visual adaptation recipes.

Recipes can select only renderer variants that already exist in the frontend.
They never contain executable code, CSS, HTML, or trusted metric values.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SAFE_BLOCK_TYPES = {"adaptive_story"}
SAFE_VARIANTS = {"mosaic", "signals", "steps", "split"}
MAX_RECIPES = 40


def load_visual_recipes(workspace_dir: Path, project_id: str | None) -> list[dict[str, Any]]:
    path = _registry_path(workspace_dir, project_id)
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    recipes = payload.get("recipes", []) if isinstance(payload, dict) else []
    return [recipe for recipe in (_normalize_recipe(item) for item in recipes) if recipe][:MAX_RECIPES]


def learn_visual_recipes(
    workspace_dir: Path,
    project_id: str | None,
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    path = _registry_path(workspace_dir, project_id)
    if path is None:
        return []
    existing = load_visual_recipes(workspace_dir, project_id)
    by_id = {str(item["id"]): item for item in existing}
    for raw in proposals:
        recipe = _normalize_recipe(raw)
        if recipe:
            previous = by_id.get(str(recipe["id"]), {})
            recipe["uses"] = int(previous.get("uses", 0)) + 1
            by_id[str(recipe["id"])] = recipe
    recipes = list(by_id.values())[-MAX_RECIPES:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "recipes": recipes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return recipes


def match_visual_recipe(section_title: str, recipes: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = _normalize_text(section_title)
    best: tuple[int, dict[str, Any]] | None = None
    for raw in recipes:
        recipe = _normalize_recipe(raw)
        if not recipe:
            continue
        scores = [
            5 if _normalize_text(cue) == normalized else 1
            for cue in recipe["cues"]
            if _normalize_text(cue) in normalized
        ]
        score = sum(scores)
        if score < 2:
            continue
        if score and (best is None or score > best[0]):
            best = (score, recipe)
    return best[1] if best else None


def _normalize_recipe(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    block_type = str(raw.get("block_type") or "adaptive_story")
    variant = str(raw.get("variant") or "mosaic")
    cues = [
        str(cue).strip()[:40]
        for cue in raw.get("cues", [])
        if isinstance(cue, (str, int, float)) and str(cue).strip()
    ][:8]
    if block_type not in SAFE_BLOCK_TYPES or variant not in SAFE_VARIANTS or not cues:
        return None
    cue_digest = hashlib.sha1("|".join(cues).encode("utf-8")).hexdigest()[:12]
    recipe_id = str(raw.get("id") or f"recipe_{cue_digest}")
    return {
        "id": re.sub(r"[^a-zA-Z0-9_-]", "_", recipe_id)[:80],
        "block_type": block_type,
        "variant": variant,
        "cues": cues,
        "intent": str(raw.get("intent") or "")[:240],
        "learned_from": str(raw.get("learned_from") or raw.get("source_section") or "")[:120],
        "uses": _safe_nonnegative_int(raw.get("uses")),
    }


def _registry_path(workspace_dir: Path, project_id: str | None) -> Path | None:
    if not project_id:
        return None
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id)
    if not safe_id:
        return None
    return workspace_dir / "projects" / safe_id / "visual-recipes.json"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0
