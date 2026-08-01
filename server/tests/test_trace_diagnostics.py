from __future__ import annotations

import json

from app.agent.trace_diagnostics import (
    _artifact_binding_summary,
    _context_budget_summary,
    _failure_analysis,
    _finalizer_diagnostics,
    _llm_diagnostics,
    classify_failure_mode,
    count_report_features,
    safe_preview,
    summarize_artifact_binding,
    summarize_context_budget,
)


class TestSafePreview:
    def test_short_text_no_truncation(self):
        result = safe_preview("hello world")
        assert result["chars"] == 11
        assert result["head"] == "hello world"
        assert result["tail"] == ""
        assert result["truncated"] is False

    def test_long_text_truncated(self):
        long_text = "a" * 3000
        result = safe_preview(long_text, head=1200, tail=1200)
        assert result["chars"] == 3000
        assert result["truncated"] is True
        assert len(result["head"]) == 1200
        assert len(result["tail"]) == 1200

    def test_none_input(self):
        result = safe_preview(None)
        assert result["chars"] == 0

    def test_empty_string(self):
        result = safe_preview("")
        assert result["chars"] == 0
        assert result["truncated"] is False


class TestCountReportFeatures:
    def test_empty_report(self):
        features = count_report_features("")
        assert features["report_md_chars"] == 0
        assert features["heading_count"] == 0
        assert features["empty_or_tiny"] is True

    def test_full_report(self):
        report = """# Executive Summary

This is a summary of findings. The data shows significant growth in Q3 compared to Q2 across all product categories with the most notable increase in premium products.

## Data Analysis

| Metric | Value |
|--------|-------|
| Sales  | 100   |

![Chart](chart_trend.html)

Evidence from source data shows consistent upward trends.

## Key Findings

The analysis reveals three primary insights that drive business decisions.

| Category | Growth | Risk |
|----------|--------|------|
| Premium  | +25%   | Low  |
| Standard | +10%   | Med  |

## Recommendations

Based on the evidence collected, we recommend increasing investment in premium products and monitoring standard product margins closely.
"""
        features = count_report_features(report)
        assert features["heading_count"] >= 2
        assert features["empty_or_tiny"] is False


class TestSummarizeContextBudget:
    def test_basic_message_count(self):
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        summary = summarize_context_budget(messages)
        assert summary["message_count"] == 3
        assert summary["estimated_context_chars"] > 0

    def test_tool_result_chars(self):
        messages = [
            {"role": "tool", "content": "x" * 1000},
        ]
        summary = summarize_context_budget(messages)
        assert summary["tool_result_chars"] == 1000

    def test_tool_call_arguments(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "t1",
                        "type": "function",
                        "function": {
                            "name": "execute_code",
                            "arguments": "y" * 500,
                        },
                    }
                ],
            }
        ]
        summary = summarize_context_budget(messages)
        assert summary["tool_call_argument_chars"] == 500


class TestClassifyFailureMode:
    def test_repeated_length_truncation(self):
        events = [
            {"type": "llm_request_completed", "data": {"finish_reason": "length"}},
            {"type": "llm_request_completed", "data": {"finish_reason": "length"}},
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 19}},
        ]
        run = {}
        result = classify_failure_mode(run, events)
        assert result["likely_failure_mode"] == "repeated_finalizer_length_truncation"
        assert result["empty_or_tiny_report"] is True
        assert result["llm_length_truncation_count"] == 2

    def test_evidence_generated_but_empty_report(self):
        events = [
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 100}},
        ]
        run = {
            "artifacts": [
                {"type": "table", "name": "t1"},
                {"type": "chart", "name": "c1"},
            ]
        }
        result = classify_failure_mode(run, events)
        assert result["likely_failure_mode"] == "evidence_generated_but_empty_report"
        assert result["evidence_generation_completed"] is True
        assert result["likely_failure_stage"] == "final_report_synthesis"

    def test_no_failure(self):
        events = [
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 5000}},
        ]
        run = {"artifacts": [{"type": "table", "name": "t1"}]}
        result = classify_failure_mode(run, events)
        assert result["empty_or_tiny_report"] is False

    def test_detached_finalizer_tracking(self):
        events = [
            {"type": "planner_detached_finalizer_started"},
            {"type": "planner_finalization_forced"},
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 5000}},
        ]
        run = {}
        result = classify_failure_mode(run, events)
        assert result["detached_finalizer_used"] is True
        assert result["force_finalize_used"] is True

    def test_force_finalize_detected_from_llm_request_started(self):
        events = [
            {"type": "llm_request_started", "data": {"iteration": 1, "force_finalize": True}},
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 500}},
        ]
        run = {"artifacts": [{"type": "table", "name": "t1"}]}
        result = classify_failure_mode(run, events)
        assert result["force_finalize_used"] is True, (
            "force_finalize_used must be detected from llm_request_started.force_finalize=True"
        )


class TestSummarizeArtifactBinding:
    def test_counts_by_type(self):
        run = {
            "artifacts": [
                {"type": "table", "name": "t1"},
                {"type": "table", "name": "t2"},
                {"type": "chart", "name": "c1"},
                {"type": "visual_report", "name": "r1"},
            ]
        }
        result = summarize_artifact_binding(run)
        assert result["table_artifacts"] == 2
        assert result["chart_artifacts"] == 1
        assert result["visual_report_count"] == 1
        assert result["has_evidence"] is True

    def test_empty_artifacts(self):
        run = {"artifacts": []}
        result = summarize_artifact_binding(run)
        assert result["has_evidence"] is False


class TestLLMDiagnostics:
    def test_counts_length_truncations(self):
        events = [
            {"type": "llm_request_completed", "data": {"iteration": 1, "finish_reason": "length"}},
            {"type": "llm_request_completed", "data": {"iteration": 2, "finish_reason": "stop"}},
            {"type": "llm_request_completed", "data": {"iteration": 3, "finish_reason": "length"}},
        ]
        result = _llm_diagnostics(events)
        assert result["length_truncation_count"] == 2
        assert result["request_count"] == 3

    def test_sums_tokens(self):
        events = [
            {
                "type": "llm_request_completed",
                "data": {
                    "iteration": 1,
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                    "latency_ms": 2000,
                },
            },
        ]
        result = _llm_diagnostics(events)
        assert result["total_prompt_tokens"] == 100
        assert result["total_completion_tokens"] == 50
        assert result["total_latency_ms"] == 2000


class TestFinalizerDiagnostics:
    def test_tracks_events(self):
        events = [
            {"type": "planner_detached_finalizer_started"},
            {"type": "planner_finalization_forced"},
            {"type": "planner_final_output_rejected"},
            {"type": "planner_payload_invalid"},
        ]
        result = _finalizer_diagnostics(events)
        assert result["detached_finalizer_used"] is True
        assert result["force_finalize_used"] is True
        assert result["format_repair_attempt_count"] == 1
        assert result["schema_repair_attempt_count"] == 1

    def test_force_finalize_from_llm_request_started(self):
        events = [
            {"type": "llm_request_started", "data": {"iteration": 3, "force_finalize": True}},
        ]
        result = _finalizer_diagnostics(events)
        assert result["force_finalize_used"] is True, (
            "force_finalize_used must be detected from llm_request_started.force_finalize=True"
        )


class TestContextBudgetSummary:
    def test_tracks_snapshots(self):
        events = [
            {
                "type": "llm_request_started",
                "data": {
                    "iteration": 1,
                    "estimated_context_chars": 90000,
                    "message_count": 50,
                    "context_budget_action": "warn",
                },
            },
        ]
        result = _context_budget_summary(events)
        assert result["max_estimated_context_chars"] == 90000
        assert result["max_message_count"] == 50
        assert result["budget_warn_count"] == 1
        assert len(result["snapshots"]) == 1


class TestArtifactBindingSummary:
    def test_returns_artifact_counts(self):
        run = {
            "artifacts": [
                {"type": "table"},
                {"type": "chart"},
                {"type": "visual_report"},
            ]
        }
        result = _artifact_binding_summary(run)
        assert result["total_artifacts"] == 3
        assert result["has_evidence"] is True


class TestFailureAnalysis:
    def test_integrates_run_and_events(self):
        events = [
            {"type": "llm_request_completed", "data": {"finish_reason": "length"}},
            {"type": "llm_request_completed", "data": {"finish_reason": "length"}},
            {"type": "planner_final_payload_parsed", "data": {"report_md_chars": 19}},
        ]
        run = {"artifacts": [{"type": "table"}, {"type": "chart"}]}
        result = _failure_analysis(run, events)
        assert result["likely_failure_mode"] == "repeated_finalizer_length_truncation"
        assert result["empty_or_tiny_report"] is True


class TestCheckReportSanity:
    def test_rejects_code_contamination(self):
        from app.agent.trace_diagnostics import check_report_sanity
        report_md = (
            "[0])\n"
            "df['\u65e5\u671f'] = pd.to_datetime(df['\u65e5\u671f'])\n"
            "df.groupby('category').sum()\n"
            "print(df.head())\n"
            "</invoke>\n"
            "</parameter>\n"
        )
        result = check_report_sanity(report_md)
        assert result["report_sanity_passed"] is False
        assert result["failure_reason"] == "report_content_contaminated_by_tool_call_or_code"
        assert result["report_md_code_marker_count"] >= 2

    def test_rejects_single_marker_tiny_report(self):
        from app.agent.trace_diagnostics import check_report_sanity
        report_md = "df['col'].sum()"
        result = check_report_sanity(report_md)
        assert result["report_sanity_passed"] is False
        assert result["failure_reason"] == "report_content_contaminated_by_tool_call_or_code"

    def test_rejects_evidence_not_integrated(self):
        from app.agent.trace_diagnostics import check_report_sanity
        report_md = "# Empty Report\n\nNo charts or evidence referenced."
        result = check_report_sanity(
            report_md,
            chart_specs=[],
            chart_ref_count=0,
            evidence_ref_count=0,
            has_evidence=True,
        )
        assert result["report_sanity_passed"] is False
        assert result["failure_reason"] == "evidence_not_integrated"

    def test_passes_clean_report(self):
        from app.agent.trace_diagnostics import check_report_sanity
        report_md = (
            "# Sales Analysis\n\n"
            "Revenue grew 25% in Q3 as shown in chart_trend.html.\n\n"
            "Evidence from data analysis confirms strong growth.\n\n"
            "| Month | Revenue |\n|-------|--------|\n| Jul | 100 |\n"
        )
        result = check_report_sanity(
            report_md,
            chart_specs=[{"name": "chart_trend"}],
            chart_ref_count=1,
            evidence_ref_count=1,
            has_evidence=True,
        )
        assert result["report_sanity_passed"] is True

    def test_passes_no_evidence_no_flag(self):
        from app.agent.trace_diagnostics import check_report_sanity
        report_md = "# Simple Report\n\nJust text, no data."
        result = check_report_sanity(
            report_md,
            chart_specs=[],
            chart_ref_count=0,
            evidence_ref_count=0,
            has_evidence=False,
        )
        assert result["report_sanity_passed"] is True
