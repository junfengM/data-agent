"""Markdown parsing utilities for visual deck (extracted from visual_deck_blocks.py)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
CONTENT_SECTION_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownTable:
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]


def split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(markdown))
    if not matches:
        return [("正文", markdown.strip())]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(1).strip(), markdown[start:end].strip()))
    return sections


def split_content_sections(markdown: str) -> list[tuple[str, str]]:
    """Split at H2/H3 so paragraph-derived visuals can stay next to the source."""
    matches = list(CONTENT_SECTION_RE.finditer(markdown))
    if not matches:
        return [("正文", markdown.strip())]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(1).strip(), markdown[start:end].strip()))
    return sections


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _split_table_row(line: str) -> list[str]:
    return [_strip_markdown(cell.strip()) for cell in line.strip().strip("|").split("|")]


def _strip_markdown(text: str) -> str:
    clean = re.sub(r"`([^`]+)`", r"\1", str(text))
    clean = clean.replace("**", "").replace("__", "")
    clean = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", clean)
    return clean.strip()


def _parse_table_block(lines: list[str], title: str) -> MarkdownTable | None:
    if len(lines) < 2:
        return None
    header = _split_table_row(lines[0])
    if not header:
        return None
    rows: list[dict[str, Any]] = []
    for line in lines[1:]:
        cells = _split_table_row(line)
        if not cells or all(re.fullmatch(r":?-{2,}:?", cell.strip()) for cell in cells):
            continue
        row = {header[index]: cells[index] if index < len(cells) else "" for index in range(len(header))}
        rows.append(row)
    if not rows:
        return None
    return MarkdownTable(title=title, columns=header, rows=rows)


def parse_markdown_tables(markdown: str) -> list[MarkdownTable]:
    lines = markdown.splitlines()
    tables: list[MarkdownTable] = []
    current_title = "表格"
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("##"):
            current_title = line.lstrip("#").strip()
        if not _is_table_row(line):
            i += 1
            continue
        block_lines: list[str] = []
        while i < len(lines) and _is_table_row(lines[i].strip()):
            block_lines.append(lines[i].strip())
            i += 1
        parsed = _parse_table_block(block_lines, current_title)
        if parsed:
            tables.append(parsed)
    return tables
