"""Lightweight inline-markdown stripping for component display text.

This module is intentionally minimal and does not depend on the broader
visual-deck pipeline. Other modules that need to clean emphasis markers
from display text can import strip_inline_markdown directly.
"""


def strip_inline_markdown(value: str) -> str:
    """Remove inline Markdown formatting tokens that degrade component display.

    Strips **, __ emphasis markers. Does NOT strip backtick code spans,
    link syntax, or heading markers — those are handled elsewhere.
    """
    value = value.replace("**", "")
    value = value.replace("__", "")
    return value.strip()
