from pathlib import Path

from app.agent.visual_adaptation import (
    learn_visual_recipes,
    load_visual_recipes,
    match_visual_recipe,
)


def test_project_visual_recipes_are_safe_and_reusable(tmp_path: Path):
    proposals = [{
        "id": "feedback-signals",
        "block_type": "adaptive_story",
        "variant": "signals",
        "cues": ["用户反馈", "风险"],
        "intent": "区分正向信号和风险信号",
        "source_section": "用户反馈",
    }]

    saved = learn_visual_recipes(tmp_path, "project-1", proposals)
    loaded = load_visual_recipes(tmp_path, "project-1")

    assert saved == loaded
    assert match_visual_recipe("用户反馈与风险", loaded)["variant"] == "signals"


def test_project_visual_recipes_reject_executable_or_unknown_variants(tmp_path: Path):
    saved = learn_visual_recipes(tmp_path, "project-1", [{
        "block_type": "custom_react",
        "variant": "<script>alert(1)</script>",
        "cues": ["反馈"],
    }])

    assert saved == []


def test_project_visual_recipes_tolerate_invalid_usage_metadata(tmp_path: Path):
    saved = learn_visual_recipes(tmp_path, "project-1", [{
        "block_type": "adaptive_story",
        "variant": "mosaic",
        "cues": ["经营复盘"],
        "uses": "not-a-number",
    }])

    assert saved[0]["uses"] == 1
