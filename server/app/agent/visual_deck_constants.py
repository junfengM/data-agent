"""Shared constants for visual deck modules (extracted from visual_deck_blocks.py)."""
from typing import Any

MAX_DECK_BLOCKS = 48
MAX_TABLE_ROWS = 12

VISUAL_BLOCK_TYPES = {
    "executive_storyboard",
    "adaptive_story",
    "kpi_grid",
    "delta_bridge",
    "leaderboard_pair",
    "trend_panel",
    "composition_panel",
    "insight_banner",
    "risk_panel",
    "next_action_list",
    "page_summary",
    "decision_matrix",
    "data_quality_panel",
    "forecast_band",
    "metric_change",
    "stage_timeline",
    "comparison_grid",
}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")
