"""Shared helpers for artifact manifest building (extracted from artifact_manifest.py)."""
import re
from pathlib import Path


def _asset_path_for_package(path: str | None) -> str | None:
    """Avoid leaking local absolute paths in exported visual manifests."""
    if not path:
        return None
    if path.startswith("artifact://") or path.startswith("assets/"):
        return path
    if Path(path).is_absolute():
        return f"assets/{Path(path).name}"
    return path


def _looks_like_directory_section(title: str, content: str) -> bool:
    """Suppress file-directory/index/debug sections from the main report body."""
    text = f"{title}\n{content}".lower()
    index_patterns = [
        "图表索引", "图表清单", "chart index", "chart list",
        "文件清单", "artifact index", "artifact list",
    ]
    debug_patterns = [
        "check working directory", "find dataset file path", "verify generated artifacts",
    ]
    return any(p in text for p in index_patterns + debug_patterns)


def _normalize_markdown_heading(title: str, content: str, raw_level: int, *, has_h1: bool) -> tuple[str, int]:
    """Keep one H1; make shell sections H2 and nested findings H3."""
    clean_title = title.strip()
    if raw_level <= 1:
        level = 1 if not has_h1 else 2
    elif raw_level == 2:
        level = 2
    else:
        level = 3

    # Heuristic: LLMs often emit every finding as H2. Keep such items nested.
    finding_markers = ("发现", "finding", "insight", "diagnosis", "诊断：")
    if level == 2 and any(marker in clean_title.lower() for marker in finding_markers):
        if re.search(r"\d|一|二|三|四|五|六|七|八|九", clean_title):
            level = 3
    return f"{'#' * level} {clean_title}" + (f"\n\n{content.strip()}" if content.strip() else ""), level


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    return {token for token in cleaned.split() if len(token) > 1}


def content_matches_name(content_lower: str, name: str) -> bool:
    if name in content_lower:
        return True
    tokens = [t for t in name.lower().replace("-", "_").replace(".", "_").split("_") if len(t) > 1]
    if not tokens:
        return False
    return all(t in content_lower for t in tokens)
