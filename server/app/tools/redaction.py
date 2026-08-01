"""Path redaction for sensitive local filesystem paths in artifacts and exports."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_LOCAL_PATH_PATTERNS = [
    re.compile(r"/Users/[^\s'\",)\]]+"),
    re.compile(r"/home/[^\s'\",)\]]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\s'\",)\]]+"),
]

_WORKSPACE_REDACTION = "<workspace>"

_ARTIFACT_SUFFIXES = frozenset({".html", ".png", ".jpg", ".jpeg", ".svg", ".csv", ".json"})


def safe_file_artifact_ref(value: str | None) -> str:
    """Preserve artifact filenames, redact everything else.

    Known artifact extensions (html, png, etc.) keep their filename only.
    Unknown paths are redacted through the normal path redaction pipeline.
    """
    if not value:
        return ""
    name = Path(str(value)).name
    if Path(name).suffix.lower() in _ARTIFACT_SUFFIXES:
        return name
    return redact_local_paths(str(value))


def redact_local_paths(
    value: Any,
    *,
    workspace_root: Path | None = None,
) -> Any:
    """Replace local filesystem paths with placeholders.

    - Paths under workspace_root become ``<workspace>/relative/path``.
    - Other /Users/, /home/, C:\\Users\\ paths become ``<local_path>``.
    - Recurses into dicts and lists.
    - Preserves filenames in artifact references when possible.
    """
    if isinstance(value, str):
        return _redact_string(value, workspace_root)
    if isinstance(value, Path):
        return _redact_string(str(value), workspace_root)
    if isinstance(value, dict):
        return {k: redact_local_paths(v, workspace_root=workspace_root) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_local_paths(item, workspace_root=workspace_root) for item in value]
    return value


def _redact_string(text: str, workspace_root: Path | None = None) -> str:
    if workspace_root is not None:
        ws = str(workspace_root).rstrip("/")
        if text.startswith(ws):
            return _WORKSPACE_REDACTION + text[len(ws):]

    for pattern in _LOCAL_PATH_PATTERNS:
        if pattern.search(text):
            return pattern.sub("<local_path>", text)
    return text
