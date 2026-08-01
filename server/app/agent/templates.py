"""Template registry — maps analysis skills to report templates."""
from pathlib import Path

from app.agent.skills import _safe_relative_markdown_path
from app.agent.skills import SkillRouter


class TemplateRegistry:
    """Loads report templates from a directory and maps skills to templates.

    Template aliases are loaded from config/skill-routing.yaml. When a skill
    has no explicit alias, the skill id itself (with underscores normalized)
    is tried as a template name.
    """

    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir
        self._cache: dict[str, str] = {}

    def template_for_skill(self, skill_id: str) -> str | None:
        candidates = [
            skill_id.replace("-", "_"),
            skill_id,
        ]
        aliases = SkillRouter.template_aliases()
        if skill_id in aliases:
            candidates.append(aliases[skill_id])
        for name in candidates:
            content = self._load(name)
            if content is not None:
                return content
        return None

    def template_for_intent(self, intent: str) -> str | None:
        return self._load(intent)

    def _load(self, name: str) -> str | None:
        if name in self._cache:
            return self._cache[name]

        path = _safe_relative_markdown_path(self.templates_dir, name)
        if path is None or not path.exists() or not path.is_file():
            return None

        content = path.read_text(encoding="utf-8")
        self._cache[name] = content
        return content
