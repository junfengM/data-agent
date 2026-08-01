from __future__ import annotations

from pathlib import Path


YAML_SUFFIXES = {".yaml", ".yml"}


class PathSafetyError(ValueError):
    pass


def resolve_project_yaml_path(
    *,
    workspace_dir: Path,
    project_id: str,
    requested_path: str,
    default_filename: str = "semantic-layer.yaml",
) -> Path:
    """Resolve a project-scoped YAML path under workspace/projects/{project_id}.

    Relative paths are interpreted under the project directory. Absolute paths are
    accepted only when they already resolve inside the project directory. Symlink
    targets are rejected when the destination exists.
    """
    project_dir = (workspace_dir / "projects" / project_id).resolve()
    raw_path = Path(requested_path or default_filename)
    candidate = raw_path if raw_path.is_absolute() else project_dir / raw_path
    resolved_candidate = candidate.resolve(strict=False)

    if resolved_candidate.suffix.lower() not in YAML_SUFFIXES:
        raise PathSafetyError("Path must point to a .yaml or .yml file")

    if candidate.exists() and candidate.is_symlink():
        raise PathSafetyError("Path must not be a symlink")

    if not resolved_candidate.is_relative_to(project_dir):
        raise PathSafetyError("Path must stay inside the project workspace")

    return resolved_candidate
