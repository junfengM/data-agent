from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import yaml

from app.models.schemas import SkillSummary

_SAFE_FILE_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


def _safe_relative_markdown_path(base_dir: Path, name: str) -> Path | None:
    """Build a path for ``name.md`` that is guaranteed to stay inside base_dir.

    Returns ``None`` for names that could escape the base directory (path
    traversal, absolute paths, or non-regular identifiers) so callers can
    treat them as "not found" instead of reading an arbitrary file.
    """
    if not _SAFE_FILE_NAME_RE.fullmatch(name):
        return None
    base = base_dir.resolve()
    candidate = (base / f"{name}.md").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


class SkillRegistry:
    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir

    def list_skills(self) -> list[SkillSummary]:
        skills: list[SkillSummary] = []
        for path in sorted(self.skills_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            skills.append(
                SkillSummary(
                    id=path.stem,
                    name=self._read_field(text, "Name") or path.stem.replace("-", " ").title(),
                    trigger=self._read_field(text, "Use When") or "",
                    path=path,
                )
            )
        return skills

    def load_skill_content(self, skill_id: str) -> str | None:
        path = _safe_relative_markdown_path(self.skills_dir, skill_id)
        if path is not None and path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    @staticmethod
    def _read_field(text: str, field: str) -> str | None:
        prefix = f"{field}:"
        for line in text.splitlines():
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        return None

    @staticmethod
    def _parse_skill_refs(text: str) -> list[str]:
        """Extract $skill-name references from text, excluding $user-context."""
        import re
        refs = re.findall(r'\$([a-zA-Z][a-zA-Z0-9_-]+)', text)
        return [r for r in refs if r != "user-context"]


@lru_cache(maxsize=1)
def _load_routing_config() -> dict:
    """Load skill-routing.yaml from the config directory. Cached per process."""
    config_path = Path(__file__).resolve().parents[3] / "config" / "skill-routing.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class SkillRouter:
    """Deterministic question-to-skill routing without LLM dependency.

    Routes are loaded from config/skill-routing.yaml. Falls back to
    'product-analysis' when no pattern matches.
    """

    _routes_cache: list[tuple[list[str], str]] | None = None
    _default_skill_cache: str | None = None

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._routes_cache is not None:
            return
        config = _load_routing_config()
        cls._routes_cache = [
            (list(entry["triggers"]), entry["skill"])
            for entry in config.get("routes", [])
        ]
        cls._default_skill_cache = config.get("default_skill", "product-analysis")

    @classmethod
    def route(cls, question: str) -> str:
        cls._ensure_loaded()
        lower = question.lower()
        for patterns, skill_id in cls._routes_cache:  # type: ignore[union-attr]
            for p in patterns:
                if p.lower() in lower:
                    return skill_id
        return cls._default_skill_cache or "product-analysis"

    @classmethod
    def route_with_reason(cls, question: str) -> tuple[str, str]:
        cls._ensure_loaded()
        lower = question.lower()
        for patterns, skill_id in cls._routes_cache:  # type: ignore[union-attr]
            for p in patterns:
                if p.lower() in lower:
                    return skill_id, p
        return cls._default_skill_cache or "product-analysis", "default"

    @classmethod
    def template_aliases(cls) -> dict[str, str]:
        """Return skill_id → template_name overrides from config."""
        config = _load_routing_config()
        return dict(config.get("template_aliases", {}) or {})
