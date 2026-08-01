from __future__ import annotations

import os

from app.agent.planner import Planner


def make_test_planner():
    os.environ.setdefault("DATA_AGENT_OPENAI_API_KEY", "test-key")
    from app.models.schemas import ModelConfigSummary
    config = ModelConfigSummary(
        id="test-model",
        provider="openai",
        model="test-model",
        api_key_env="DATA_AGENT_OPENAI_API_KEY",
        base_url="http://localhost",
        temperature=0.2,
        max_tokens=None,
    )
    return Planner(config)


class TestDetachedFinalizerMessages:
    def test_messages_have_no_tool_calls(self):
        planner = make_test_planner()
        messages = planner._build_detached_finalizer_messages(
            question="分析销售趋势",
            profiles=[],
            analysis_intent={"expected_output": "report"},
            execution_results=[
                {
                    "name": "step1",
                    "status": "completed",
                    "returncode": 0,
                    "stdout": "sales=123",
                    "tables": [
                        {
                            "name": "monthly",
                            "rows": 7,
                            "columns": ["月份", "销售额"],
                            "preview": [],
                        }
                    ],
                    "charts": [
                        {"name": "chart1", "type": "html", "path": "chart1.html"}
                    ],
                }
            ],
            latest_feedback=None,
            reason="test",
        )
        assert len(messages) == 2
        assert all("tool_calls" not in m for m in messages)
        assert "monthly" in messages[1]["content"]
        assert "chart1.html" in messages[1]["content"]

    def test_omits_full_generated_code(self):
        planner = make_test_planner()
        messages = planner._build_detached_finalizer_messages(
            question="分析",
            profiles=[],
            analysis_intent={},
            execution_results=[
                {
                    "name": "step1",
                    "status": "completed",
                    "returncode": 0,
                    "code": "print('x')" * 10000,
                    "code_ref": "step1",
                    "code_chars": 100000,
                    "stdout": "",
                    "tables": [],
                    "charts": [],
                }
            ],
            latest_feedback=None,
            reason="test",
        )
        content = messages[1]["content"]
        assert "print('x')" not in content

    def test_preserves_table_and_chart_refs(self):
        planner = make_test_planner()
        messages = planner._build_detached_finalizer_messages(
            question="分析",
            profiles=[],
            analysis_intent={},
            execution_results=[
                {
                    "name": "s1",
                    "status": "completed",
                    "returncode": 0,
                    "stdout": "",
                    "tables": [
                        {
                            "name": "sales_table",
                            "rows": 10,
                            "columns": ["product", "revenue"],
                            "preview": [{"product": "A", "revenue": 100}],
                            "path": "sales_table.csv",
                        }
                    ],
                    "charts": [
                        {"name": "trend", "type": "html", "path": "trend.html"}
                    ],
                }
            ],
            latest_feedback=None,
            reason="test",
        )
        content = messages[1]["content"]
        assert "sales_table" in content
        assert "trend" in content
        assert "trend.html" in content

    def test_failed_steps_in_separate_summary(self):
        planner = make_test_planner()
        messages = planner._build_detached_finalizer_messages(
            question="分析",
            profiles=[],
            analysis_intent={},
            execution_results=[
                {
                    "name": "bad_step",
                    "status": "failed",
                    "returncode": 1,
                    "stderr": "NameError: x not defined",
                    "tables": [{"name": "partial_table", "partial": True}],
                    "charts": [],
                }
            ],
            latest_feedback=None,
            reason="test",
        )
        content = messages[1]["content"]
        assert "failed_steps" in content
        assert "NameError" in content
        assert "bad_step" in content

    def test_includes_latest_feedback(self):
        planner = make_test_planner()
        messages = planner._build_detached_finalizer_messages(
            question="分析",
            profiles=[],
            analysis_intent={},
            execution_results=[],
            latest_feedback={
                "passed": False,
                "hard_failure_count": 1,
                "quality_miss_count": 2,
                "quality_score": 0.5,
                "summary": "Need deeper analysis",
            },
            reason="test",
        )
        content = messages[1]["content"]
        assert "Need deeper analysis" in content
        assert "hard_failure_count" in content

    def test_includes_dataset_profiles(self):
        from app.models.schemas import ColumnProfile, DatasetProfile
        planner = make_test_planner()

        profile = DatasetProfile(
            dataset_id="ds-1",
            filename="sales.csv",
            row_count=1000,
            column_count=2,
            columns=[
                ColumnProfile(
                    name="date",
                    dtype="str",
                    non_null_count=1000,
                    null_count=0,
                    null_pct=0.0,
                    unique_count=365,
                    sample_values=[],
                ),
                ColumnProfile(
                    name="amount",
                    dtype="float64",
                    non_null_count=998,
                    null_count=2,
                    null_pct=0.2,
                    unique_count=900,
                    sample_values=[],
                ),
            ],
        )

        messages = planner._build_detached_finalizer_messages(
            question="分析",
            profiles=[profile],
            analysis_intent={},
            execution_results=[],
            latest_feedback=None,
            reason="test",
        )
        content = messages[1]["content"]
        assert "sales.csv" in content
        assert "date" in content
        assert "amount" in content

    def test_bundle_under_budget_with_realistic_evidence(self):
        planner = make_test_planner()
        tables = []
        for i in range(5):
            cols = [f"col_{j}" for j in range(10)]
            preview = [{c: j * 10 for c in cols} for j in range(3)]
            tables.append({
                "name": f"table_{i}",
                "rows": 50,
                "columns": cols,
                "preview": preview,
            })
        charts = [
            {"name": f"chart_{i}", "type": "html", "path": f"chart_{i}.html"}
            for i in range(3)
        ]
        results = [
            {
                "name": f"step_{i}",
                "description": f"desc_{i}",
                "status": "completed",
                "returncode": 0,
                "stdout": "key=123\nratio=45%" * 10,
                "tables": tables[i : i + 1],
                "charts": charts if i == 0 else [],
            }
            for i in range(5)
        ]

        messages = planner._build_detached_finalizer_messages(
            question="分析销售数据趋势、品类结构、渠道对比、会员分层",
            profiles=[],
            analysis_intent={"expected_output": "report"},
            execution_results=results,
            latest_feedback=None,
            reason="context_budget",
        )

        bundle_chars = len(messages[1]["content"])
        assert bundle_chars < 60000, f"Bundle too large: {bundle_chars} chars"


class TestDetachedFinalizerDisabled:
    def test_detached_finalizer_flag_is_false(self):
        from app.agent.planner import ENABLE_DETACHED_FINALIZER
        assert ENABLE_DETACHED_FINALIZER is False

    def test_coerce_final_payload_returns_dict_or_none(self):
        planner = make_test_planner()
        result = planner._coerce_final_payload(
            "not valid json at all",
            question="test",
            analysis_intent={},
            force_finalize=True,
        )
        assert isinstance(result, dict) or result is None

    def test_coerce_final_payload_with_truncated_json(self):
        planner = make_test_planner()
        result = planner._coerce_final_payload(
            '{"title": "Report", "summary',
            question="test",
            analysis_intent={},
            force_finalize=True,
        )
        assert isinstance(result, dict) or result is None


class TestCoerceFinalPayloadRejection:
    def test_force_finalize_blank_output_rejected_when_evidence_exists(self):
        planner = make_test_planner()
        result = planner._coerce_final_payload(
            "   ",
            question="test question",
            analysis_intent={},
            force_finalize=True,
            has_successful_evidence=True,
            min_report_chars=300,
        )
        assert result is None, "Blank/whitespace content must be rejected when evidence exists"

    def test_force_finalize_tiny_output_rejected_when_evidence_exists(self):
        planner = make_test_planner()
        result = planner._coerce_final_payload(
            "ok",
            question="test question",
            analysis_intent={},
            force_finalize=True,
            has_successful_evidence=True,
            min_report_chars=300,
        )
        assert result is None, "Tiny content (< min_report_chars) must be rejected when evidence exists"

    def test_force_finalize_short_output_accepted_without_evidence(self):
        planner = make_test_planner()
        result = planner._coerce_final_payload(
            "short report",
            question="test question",
            analysis_intent={},
            force_finalize=True,
            has_successful_evidence=False,
            min_report_chars=300,
        )
        assert isinstance(result, dict), "Short content without evidence should still be accepted"

    def test_force_finalize_valid_report_accepted_with_evidence(self):
        planner = make_test_planner()
        long_report = "# Analysis Report\n\nThis is a comprehensive analysis with sufficient content " + "data " * 100
        result = planner._coerce_final_payload(
            long_report,
            question="test question",
            analysis_intent={},
            force_finalize=True,
            has_successful_evidence=True,
            min_report_chars=300,
        )
        assert result is not None
        assert isinstance(result, dict)
        assert len(result.get("report_md", "")) >= 300

    def test_json_payload_with_short_report_md_rejected_when_evidence_exists(self):
        planner = make_test_planner()
        import json
        content = json.dumps({"report_md": "too short", "title": "T"})
        result = planner._coerce_final_payload(
            content,
            question="test",
            analysis_intent={},
            force_finalize=True,
            has_successful_evidence=True,
            min_report_chars=300,
        )
        assert result is None, "JSON with short report_md must be rejected when evidence exists"
