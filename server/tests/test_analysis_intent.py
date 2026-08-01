from app.agent.feedback import evaluate_attempt_feedback
from app.agent.planner import (
    MAX_FEEDBACK_REPAIR_ROUNDS,
    Planner,
)
from app.agent.intent import infer_analysis_intent
from app.models.schemas import CandidateAngle, ColumnProfile, DatasetProfile


def _profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_id="ds1",
        filename="sales.csv",
        row_count=100,
        column_count=4,
        columns=[
            ColumnProfile(name="month", dtype="string", non_null_count=100, null_count=0, null_pct=0, unique_count=12),
            ColumnProfile(name="region", dtype="string", non_null_count=100, null_count=0, null_pct=0, unique_count=4),
            ColumnProfile(name="revenue", dtype="float", non_null_count=100, null_count=0, null_pct=0, unique_count=90),
            ColumnProfile(name="orders", dtype="int", non_null_count=100, null_count=0, null_pct=0, unique_count=80),
        ],
    )


def test_infer_analysis_intent_extracts_task_metrics_and_dimensions():
    intent = infer_analysis_intent(
        question="分析收入下降原因，按区域和月份拆解",
        profiles=[_profile()],
    )

    assert intent["task_type"] == "diagnosis"
    assert intent["expected_output"] == "deep_dive"
    assert "revenue" in intent["primary_metrics"]
    assert "month" in intent["dimensions"]
    assert "region" in intent["dimensions"]
    assert intent["confidence"] > 0.5


def test_feedback_flags_incomplete_candidate_angles():
    feedback = evaluate_attempt_feedback(
        question="看看有什么机会",
        report_md="# 结论\n\n建议优先处理区域差异，收入差异达到 12%。",
        execution_results=[
            {
                "name": "overview",
                "description": "Revenue overview",
                "returncode": 0,
                "status": "completed",
                "stdout": "revenue delta 12%",
                "tables": [{"name": "summary"}],
                "charts": [],
            },
            {
                "name": "segment",
                "description": "Segment deep dive",
                "returncode": 0,
                "status": "completed",
                "stdout": "region gap 12%",
                "tables": [{"name": "segment"}],
                "charts": [],
            },
        ],
        candidate_angles=[
            {
                "id": "a1",
                "question": "Revenue by region",
                "dimensions": ["region"],
                "measures": [],
                "expected_evidence": "",
                "selected": True,
            }
        ],
        data_backed=True,
    )

    assert feedback["should_retry"] is True
    assert any(item["source"] == "angle_schema" for item in feedback["items"])


def test_feedback_requires_chart_before_visual_report_finalization():
    feedback = evaluate_attempt_feedback(
        question="分析销售趋势并生成报告",
        report_md="# 结论\n\n12 月销售额增长 48%，建议提前备货。",
        execution_results=[
            {
                "name": "monthly_trend",
                "returncode": 0,
                "status": "completed",
                "stdout": "12月增长48%",
                "tables": [{"name": "monthly_trend"}],
                "charts": [],
            },
        ],
        data_backed=True,
        analysis_intent={"expected_output": "report"},
    )

    assert feedback["should_retry"] is True
    assert any(item["source"] == "visual_evidence" for item in feedback["items"])


def test_feedback_passes_covered_selected_angle():
    feedback = evaluate_attempt_feedback(
        question="分析收入按区域的机会",
        report_md="# 结论\n\n建议优先优化华东区域。收入提升机会为 12%，见分区域分析。",
        execution_results=[
            {
                "name": "region_revenue",
                "description": "a1 Revenue by region",
                "angle_id": "a1",
                "returncode": 0,
                "status": "completed",
                "stdout": "region revenue gap 12%",
                "tables": [{"name": "region_revenue"}],
                "charts": [{"name": "region_revenue", "type": "bar"}],
            },
            {
                "name": "region_driver",
                "description": "driver deep dive",
                "returncode": 0,
                "status": "completed",
                "stdout": "driver contribution 8%",
                "tables": [{"name": "region_driver"}],
                "charts": [],
            },
        ],
        candidate_angles=[
            {
                "id": "a1",
                "question": "Revenue by region",
                "dimensions": ["region"],
                "measures": ["revenue"],
                "expected_evidence": "bar chart and contribution table",
                "impact_score": 0.8,
                "confidence_score": 0.8,
                "actionability_score": 0.8,
                "novelty_score": 0.2,
                "relevance_score": 0.9,
                "data_sufficiency_score": 0.9,
                "selected": True,
                "rejected_reason": None,
            }
        ],
        analysis_intent={"primary_metrics": ["revenue"], "expected_output": "deep_dive"},
        data_backed=True,
    )

    assert not any(item["source"] == "angle_coverage" for item in feedback["items"])


def test_feedback_does_not_block_on_repaired_execution_step():
    feedback = evaluate_attempt_feedback(
        question="分析收入趋势并给出建议",
        report_md="# 结论\n\n收入增长 12%，建议继续跟进重点渠道。",
        execution_results=[
            {
                "name": "data_inspection",
                "returncode": 1,
                "status": "failed",
                "stderr": "FileNotFoundError",
                "tables": [],
                "charts": [],
            },
            {
                "name": "data_inspection_repaired",
                "returncode": 0,
                "status": "completed",
                "stdout": "revenue growth 12%",
                "tables": [{"name": "monthly_revenue"}],
                "charts": [{"name": "monthly_revenue", "type": "line"}],
            },
        ],
        data_backed=True,
    )

    assert not any(item["source"] == "execution_result" for item in feedback["items"])


def test_feedback_treats_chinese_section_repair_as_resolving_failure():
    feedback = evaluate_attempt_feedback(
        question="分析月度趋势",
        report_md="# 结论\n\n12 月销售额增长 48%，建议提前备货。",
        execution_results=[
            {
                "name": "Section A: 月度趋势分析（优化版）",
                "returncode": 1,
                "status": "failed",
                "stderr": "ValueError",
                "tables": [],
                "charts": [],
            },
            {
                "name": "Section A: 月度趋势分析（修正版）",
                "returncode": 0,
                "status": "completed",
                "stdout": "12月增长48%",
                "tables": [{"name": "monthly_trend"}],
                "charts": [],
            },
        ],
        data_backed=True,
    )

    assert not any(item["source"] == "execution_result" for item in feedback["items"])


def test_feedback_uses_explicit_repair_of_when_step_name_changes():
    feedback = evaluate_attempt_feedback(
        question="分析月度趋势",
        report_md="# 结论\n\n12 月销售额增长 48%，建议提前备货。",
        execution_results=[
            {
                "name": "Deep dive: C2 brands and seasonal pattern attribution",
                "returncode": 1,
                "status": "failed",
                "stderr": "KeyError",
                "tables": [],
                "charts": [],
            },
            {
                "name": "Seasonal pattern and remaining brand deep dive",
                "repair_of": "Deep dive: C2 brands and seasonal pattern attribution",
                "returncode": 0,
                "status": "completed",
                "tables": [{"name": "seasonal_pattern"}],
                "charts": [],
            },
        ],
        data_backed=True,
    )

    assert not any(item["source"] == "execution_result" for item in feedback["items"])


def test_planner_stops_retrying_feedback_at_repair_limit():
    feedback = {
        "should_retry": True,
        "hard_failure_count": 1,
    }

    assert Planner._should_retry_feedback(
        feedback,
        MAX_FEEDBACK_REPAIR_ROUNDS,
    ) is False


def test_planner_prompt_requires_injected_dataset_paths():
    assert "dataset_paths" in Planner._build_run_prompt(
        question="分析销售趋势",
        profiles=[_profile()],
        project_contexts=None,
        ad_hoc_context=None,
    )


def test_planner_execution_budget_removes_execute_code(monkeypatch):
    monkeypatch.setenv("T", "fake-key")
    from app.core.model_config import ModelConfigSummary
    planner = Planner(ModelConfigSummary(
        id="test", provider="openai", api_key_env="T", model="gpt-4",
    ))
    names = [tool["function"]["name"] for tool in planner._available_tools(0)]

    assert "execute_code" in names
    assert "save_semantic_finding" in names
    assert "evaluate_attempt" not in names

    names_at_budget = [
        tool["function"]["name"]
        for tool in planner._available_tools(10_000)
    ]
    assert "execute_code" not in names_at_budget
    assert "save_semantic_finding" not in names_at_budget
    assert "load_skill" in names_at_budget


def test_planner_normalizes_candidate_angle_scores_from_ten_point_scale():
    angles = Planner._normalize_candidate_angles([
        {
            "question": "Which month performed best?",
            "dimensions": "month",
            "measures": ["revenue"],
            "impact_score": 9,
            "confidence_score": 10,
            "actionability_score": 8,
            "novelty_score": 5,
            "relevance_score": 10,
            "data_sufficiency_score": 10,
            "selected": True,
        }
    ])

    assert angles[0]["dimensions"] == ["month"]
    assert angles[0]["impact_score"] == 0.9
    assert angles[0]["confidence_score"] == 1.0
    CandidateAngle(**angles[0])


def test_planner_accepts_markdown_when_forced_finalization_json_is_invalid():
    payload = Planner._coerce_final_payload(
        "# 销售趋势分析\n\n## 结论\n\n12 月销售额最高，建议提前准备年末礼赠库存。",
        question="分析销售趋势",
        analysis_intent={"expected_output": "report"},
        force_finalize=True,
    )

    assert payload is not None
    assert payload["title"] == "销售趋势分析"
    assert payload["report_md"].startswith("# 销售趋势分析")
    assert payload["selected_skills"]


def test_planner_salvages_report_from_truncated_json_wrapper():
    content = (
        '{"title":"销售趋势分析","report_md":"# 销售趋势分析\\n\\n'
        '## 结论\\n\\n12 月销售额最高，建议提前准备年末礼赠库存。",'
        '"candidate_angles":['
    )

    payload = Planner._coerce_final_payload(
        content,
        question="分析销售趋势",
        analysis_intent={"expected_output": "report"},
        force_finalize=True,
    )

    assert payload is not None
    assert payload["report_md"].startswith("# 销售趋势分析")
    assert "12 月销售额最高" in payload["report_md"]


def test_planner_prompt_requires_run_directory_evidence_outputs():
    prompt = Planner._build_run_prompt(
        question="分析销售趋势",
        profiles=[_profile()],
        project_contexts=None,
        ad_hoc_context=None,
    )

    assert "Do not write evidence files to /tmp" in prompt
    assert "relative filename" in prompt


def test_planner_preserves_explicit_repair_link_on_execution_result():
    result = Planner._normalize_execution_result(
        {
            "step_name": "monthly trend fixed",
            "repair_of": "monthly trend",
        },
        {"status": "completed", "returncode": 0},
    )

    assert result["repair_of"] == "monthly trend"


def test_planner_normalizes_llm_visual_plan_without_accepting_values():
    plan = Planner._normalize_visual_plan([
        {
            "type": "metric_change",
            "section": "核心发现",
            "title": "转化效率提升",
            "purpose": "强调转化率的起点和终点",
            "priority": 1,
            "items": [{"start": "18.2%", "end": "26.7%"}],
        },
        {
            "type": "unsupported_widget",
            "section": "核心发现",
        },
    ])

    assert plan == [{
        "id": "visual_plan_1",
        "block_type": "metric_change",
        "source_section": "核心发现",
        "source_ref": None,
        "title": "转化效率提升",
        "intent": "强调转化率的起点和终点",
        "priority": "1",
        "options": {},
    }]


def test_length_truncation_prompt_matches_json_mode(monkeypatch):
    monkeypatch.setenv("T", "fake-key")
    from app.core.model_config import ModelConfigSummary
    from app.agent.planner import Planner
    planner = Planner(ModelConfigSummary(
        id="test", provider="openai", api_key_env="T", model="gpt-4",
    ))
    prompt = planner._finalize_prompt(None, [])
    assert "JSON" in prompt or "json" in prompt
    assert "Markdown only" not in prompt


def test_execute_step_returns_full_step_payload_with_table_preview_and_chart_path():
    from unittest.mock import AsyncMock, MagicMock
    from pathlib import Path
    from app.agent.planner_bridge import create_execute_step

    mock_emit = AsyncMock()
    run_mock = MagicMock()
    run_mock.tool_calls = []
    run_mock.artifacts = []
    step_results_list: list[dict] = []

    execute_step = create_execute_step(
        run_dir=Path("/tmp/test_run"),
        dataset_paths=[Path("/tmp/test.csv")],
        generated_code_execution="disabled",
        run=run_mock,
        emit=mock_emit,
        step_results_list=step_results_list,
    )

    import asyncio
    result = asyncio.run(execute_step("print('hello')", "test_step", "a test step"))

    assert "name" in result
    assert "returncode" in result
    assert "tables" in result
    assert "charts" in result
